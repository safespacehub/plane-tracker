package main

import (
	"fmt"
	"io"
	"log"
	"net/http"
)

func main() {
	http.HandleFunc("/ingest", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Only POST allowed", http.StatusMethodNotAllowed)
			return
		}

		body, err := io.ReadAll(r.Body)
		if err != nil {
			http.Error(w, "Error reading body", http.StatusBadRequest)
			return
		}
		defer r.Body.Close()

		// Print to console
		fmt.Printf("Received POST (%d bytes): %s\n", len(body), string(body))

		// Always respond OK
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"acked":true}`))
	})

	addr := ":8080"
	log.Println("Ingest server listening on", addr)
	log.Fatal(http.ListenAndServe(addr, nil))
}
