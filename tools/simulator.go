package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"os"
	"sync"
	"time"
)

/*
Simulates an ESP32 device that:
- Creates random sessions (one per boot)
- In each session, increments run_seconds at a fixed "device minute" interval
- Sends JSON updates to a server endpoint
- Store-and-forward: if offline or POST fails, queues and retries oldest-first
- Idempotency via msg_id = session_start:run_seconds

JSON payload sent:
{
  "device_id":     "car-esp32-01",
  "session_start": "2025-10-23T18:00:00Z",
  "run_seconds":   1200,
  "last_update":   "2025-10-23T18:20:00Z",
  "status":        "open" | "closed",
  "msg_id":        "2025-10-23T18:00:00Z:1200"
}
*/

type Update struct {
	DeviceID     string `json:"device_id"`
	SessionStart string `json:"session_start"`
	RunSeconds   int    `json:"run_seconds"`
	LastUpdate   string `json:"last_update"`
	Status       string `json:"status"`
	MsgID        string `json:"msg_id"`
}

// Outbox is a simple durable-ish queue in memory.
// Oldest-first retries; removes only when server 2xx.
type Outbox struct {
	mu   sync.Mutex
	q    []*Update
	sent int // total sent successfully (metrics)
}

func (o *Outbox) Enqueue(u *Update) {
	o.mu.Lock()
	defer o.mu.Unlock()
	o.q = append(o.q, u)
}

func (o *Outbox) PeekBatch(max int) []*Update {
	o.mu.Lock()
	defer o.mu.Unlock()
	if len(o.q) == 0 {
		return nil
	}
	if max > len(o.q) {
		max = len(o.q)
	}
	b := make([]*Update, max)
	copy(b, o.q[:max])
	return b
}

func (o *Outbox) Ack(n int) {
	o.mu.Lock()
	defer o.mu.Unlock()
	if n <= 0 {
		return
	}
	if n > len(o.q) {
		n = len(o.q)
	}
	o.q = o.q[n:]
	o.sent += n
}

type Session struct {
	StartUTC time.Time
	Duration int // target run_seconds for this session (random)
	Closed   bool
}

func main() {
	// ---- Flags / configuration ----
	var (
		ingestURL     = flag.String("url", envOr("INGEST_URL", "http://127.0.0.1:8080/ingest"), "Server ingest URL")
		deviceID      = flag.String("device", envOr("DEVICE_ID", "airplane-N20503"), "Device ID")
		sessions      = flag.Int("sessions", 5, "How many sessions to simulate")
		minDurMin     = flag.Int("minSessionMin", 5, "Minimum session duration (minutes)")
		maxDurMin     = flag.Int("maxSessionMin", 60, "Maximum session duration (minutes)")
		tickRealMS    = flag.Int("tickMS", 200, "Real milliseconds per simulated device minute")
		updateEvery   = flag.Int("updateEveryMin", 1, "Post an update every N simulated minutes")
		offlineProb   = flag.Float64("offlineProb", 0.2, "Probability [0..1] that the device is offline at a tick")
		serverErrProb = flag.Float64("serverErrProb", 0.1, "Probability [0..1] of server error (simulated client-side)")
		batchSize     = flag.Int("batch", 8, "Max queued updates to send per flush cycle")
		flushEveryMS  = flag.Int("flushEveryMS", 400, "Attempt to flush outbox every N ms")
		jitterMS      = flag.Int("jitterMS", 75, "Random jitter added to each tick (±)")
		seed          = flag.Int64("seed", time.Now().UnixNano(), "RNG seed")
		verbose       = flag.Bool("v", true, "Verbose logs")
	)
	flag.Parse()
	rand.Seed(*seed)

	log.Printf("Starting simulator: device=%s url=%s sessions=%d", *deviceID, *ingestURL, *sessions)

	client := &http.Client{Timeout: 8 * time.Second}
	outbox := &Outbox{}

	// Flush loop: periodically try to send oldest updates.
	stopFlush := make(chan struct{})
	go func() {
		t := time.NewTicker(time.Duration(*flushEveryMS) * time.Millisecond)
		defer t.Stop()
		for {
			select {
			case <-t.C:
				flushOnce(client, outbox, *ingestURL, *batchSize, *serverErrProb, *verbose)
			case <-stopFlush:
				return
			}
		}
	}()

	// Simulate sequential sessions.
	for i := 0; i < *sessions; i++ {
		sess := newRandomSession(*minDurMin, *maxDurMin)
		if *verbose {
			log.Printf("New session #%d start=%s target=%dm", i+1, sess.StartUTC.UTC().Format(time.RFC3339), sess.Duration)
		}
		simulateSession(sess, *deviceID, *ingestURL, client, outbox,
			time.Duration(*tickRealMS), *updateEvery, *offlineProb, *serverErrProb, *jitterMS, *verbose)
	}

	// Final flush attempts, then exit
	time.Sleep(2 * time.Second)
	flushDrained(client, outbox, *ingestURL, *batchSize, *serverErrProb, *verbose)
	close(stopFlush)

	log.Printf("Done. Sent=%d Pending=%d", outbox.sent, len(outbox.PeekBatch(1<<30)))
}

// newRandomSession creates a session with a random duration in minutes.
func newRandomSession(minMin, maxMin int) *Session {
	if maxMin < minMin {
		maxMin = minMin
	}
	durMin := minMin + rand.Intn(maxMin-minMin+1)
	// Start time: sometime within the last 24h
	start := time.Now().UTC().Add(-time.Duration(rand.Intn(24*60)) * time.Minute)
	return &Session{
		StartUTC: start,
		Duration: durMin * 60, // store as seconds
		Closed:   false,
	}
}

// simulateSession runs one session, producing updates and enqueueing them.
// "Device minute" advances every tickRealMS; each update increases run_seconds accordingly.
func simulateSession(
	sess *Session,
	deviceID, url string,
	client *http.Client,
	outbox *Outbox,
	tickRealMS time.Duration,
	updateEveryMin int,
	offlineProb float64,
	serverErrProb float64,
	jitterMS int,
	verbose bool,
) {
	if updateEveryMin <= 0 {
		updateEveryMin = 1
	}
	// Simulated device clock
	runSeconds := 0
	lastUpdateSentAtMin := -updateEveryMin // force first update at minute 0
	deviceMinute := 0

	for runSeconds < sess.Duration {
		// Sleep to simulate one "device minute"
		sleepMS := int(tickRealMS)
		if jitterMS > 0 {
			sleepMS += rand.Intn(2*jitterMS+1) - jitterMS
			if sleepMS < 1 {
				sleepMS = 1
			}
		}
		time.Sleep(time.Duration(sleepMS) * time.Millisecond)

		deviceMinute++
		runSeconds += 60

		// Send update every N device minutes
		if deviceMinute-lastUpdateSentAtMin >= updateEveryMin {
			lastUpdateSentAtMin = deviceMinute

			// Build update
			lastUpdateUTC := sess.StartUTC.Add(time.Duration(runSeconds) * time.Second).UTC()
			u := &Update{
				DeviceID:     deviceID,
				SessionStart: sess.StartUTC.UTC().Format(time.RFC3339),
				RunSeconds:   runSeconds,
				LastUpdate:   lastUpdateUTC.Format(time.RFC3339),
				Status:       "open",
				MsgID:        fmt.Sprintf("%s:%d", sess.StartUTC.UTC().Format(time.RFC3339), runSeconds),
			}

			// Simulate connectivity: sometimes offline
			online := rand.Float64() > offlineProb
			if !online {
				if verbose {
					log.Printf("[queue] offline -> %s run=%ds", u.SessionStart, u.RunSeconds)
				}
				outbox.Enqueue(u)
				continue
			}

			// Try immediate POST; if it fails (error or simulated server failure), queue it.
			if err := postOnce(client, url, u, serverErrProb); err != nil {
				if verbose {
					log.Printf("[queue] post failed -> %s run=%ds err=%v", u.SessionStart, u.RunSeconds, err)
				}
				outbox.Enqueue(u)
			} else if verbose {
				log.Printf("[sent ] %s run=%ds", u.SessionStart, u.RunSeconds)
			}
		}
	}

	// Close session with a final update
	sess.Closed = true
	final := &Update{
		DeviceID:     deviceID,
		SessionStart: sess.StartUTC.UTC().Format(time.RFC3339),
		RunSeconds:   sess.Duration,
		LastUpdate:   sess.StartUTC.Add(time.Duration(sess.Duration) * time.Second).UTC().Format(time.RFC3339),
		Status:       "closed",
		MsgID:        fmt.Sprintf("%s:%d", sess.StartUTC.UTC().Format(time.RFC3339), sess.Duration),
	}
	// Try send; on failure, enqueue
	if err := postOnce(client, url, final, serverErrProb); err != nil {
		if verbose {
			log.Printf("[queue] final post failed -> %s run=%ds err=%v", final.SessionStart, final.RunSeconds, err)
		}
		outbox.Enqueue(final)
	} else if verbose {
		log.Printf("[sent ] final %s run=%ds (closed)", final.SessionStart, final.RunSeconds)
	}
}

// postOnce sends a single update; returns error if failed or serverErrProb triggers a fake failure.
func postOnce(client *http.Client, url string, u *Update, serverErrProb float64) error {
	// Simulate server-side errors randomly (client-side)
	if rand.Float64() < serverErrProb {
		return fmt.Errorf("simulated server failure")
	}
	b, _ := json.Marshal(u)
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(b))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("server status %d", resp.StatusCode)
	}
	return nil
}

// flushOnce tries to send up to batchSize oldest items from the outbox.
func flushOnce(client *http.Client, outbox *Outbox, url string, batchSize int, serverErrProb float64, verbose bool) {
	batch := outbox.PeekBatch(batchSize)
	if len(batch) == 0 {
		return
	}
	sent := 0
	for _, u := range batch {
		if err := postOnce(client, url, u, serverErrProb); err != nil {
			// Stop on first failure to avoid hammering
			if verbose {
				log.Printf("[hold ] retry fail -> %s run=%ds err=%v", u.SessionStart, u.RunSeconds, err)
			}
			break
		}
		sent++
		if verbose {
			log.Printf("[flushed] %s run=%ds", u.SessionStart, u.RunSeconds)
		}
	}
	if sent > 0 {
		outbox.Ack(sent)
	}
}

// flushDrained keeps flushing until queue stops shrinking or empties.
func flushDrained(client *http.Client, outbox *Outbox, url string, batchSize int, serverErrProb float64, verbose bool) {
	for {
		before := len(outbox.PeekBatch(1 << 30))
		if before == 0 {
			return
		}
		flushOnce(client, outbox, url, batchSize, serverErrProb, verbose)
		after := len(outbox.PeekBatch(1 << 30))
		if after >= before {
			return
		}
		time.Sleep(200 * time.Millisecond)
	}
}

func envOr(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
