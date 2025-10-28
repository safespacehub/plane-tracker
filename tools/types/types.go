package types

// Update represents a session update from a device
type Update struct {
	DeviceID     string `json:"device_id"`
	SessionStart string `json:"session_start"`
	RunSeconds   int    `json:"run_seconds"`
	LastUpdate   string `json:"last_update"`
	Status       string `json:"status"`
	MsgID        string `json:"msg_id"`
}
