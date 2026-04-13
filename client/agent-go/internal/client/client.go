package client

import (
	"bytes"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"

	"github.com/cert-control-plane/agent-go/internal/config"
)

// ControlPlaneClient is the HTTP client for control plane API
type ControlPlaneClient struct {
	config     *config.Config
	baseURL    string
	httpClient *http.Client
}

// RegisterRequest is the TOFU registration request
type RegisterRequest struct {
	Name        string `json:"name"`
	Fingerprint string `json:"fingerprint"`
}

// RegisterResponse is the response from registration
type RegisterResponse struct {
	Status     string  `json:"status"`
	AgentID    string  `json:"agent_id"`
	AgentToken *string `json:"agent_token,omitempty"`
	Message    string  `json:"message"`
}

// RegisterStatusResponse is the approval status poll response
type RegisterStatusResponse struct {
	Status     string  `json:"status"`
	AgentToken *string `json:"agent_token,omitempty"`
}

// HeartbeatRequest is the request body for heartbeat
type HeartbeatRequest struct {
	Status string `json:"status"`
}

// HeartbeatResponse is the response from heartbeat
type HeartbeatResponse struct {
	Acknowledged bool `json:"acknowledged"`
}

// CertCheckItem is one entry in the batch cert check
type CertCheckItem struct {
	LocalPath       string  `json:"local_path"`
	CurrentNotAfter *string `json:"current_not_after,omitempty"`
}

// CertUpdateItem is the server's response for one cert path
type CertUpdateItem struct {
	LocalPath string  `json:"local_path"`
	HasUpdate bool    `json:"has_update"`
	CertPEM   *string `json:"cert_pem,omitempty"`
	KeyPEM    *string `json:"key_pem,omitempty"`
	ChainPEM  *string `json:"chain_pem,omitempty"`
	NotAfter  *string `json:"not_after,omitempty"`
}

// FetchCertsRequest is the batch cert fetch request
type FetchCertsRequest struct {
	Certs []CertCheckItem `json:"certs"`
}

// FetchCertsResponse is the batch cert fetch response
type FetchCertsResponse struct {
	Updates []CertUpdateItem `json:"updates"`
}

// ReportCertItem is one entry in the report-certs request
type ReportCertItem struct {
	LocalPath string  `json:"local_path"`
	CertPEM   string  `json:"cert_pem"`
	ChainPEM  *string `json:"chain_pem,omitempty"`
}

// ReportCertsRequest is the request body for reporting deployed certs
type ReportCertsRequest struct {
	Certs []ReportCertItem `json:"certs"`
}

// ReportCertsResponse is the response from report-certs
type ReportCertsResponse struct {
	Recorded int `json:"recorded"`
}

// New creates a new ControlPlaneClient (no mTLS)
func New(cfg *config.Config) (*ControlPlaneClient, error) {
	// Configure TLS
	tlsConfig := &tls.Config{}
	if cfg.InsecureSkipVerify {
		tlsConfig.InsecureSkipVerify = true
	}

	transport := &http.Transport{
		TLSClientConfig: tlsConfig,
	}

	return &ControlPlaneClient{
		config:  cfg,
		baseURL: cfg.ControlPlaneURL,
		httpClient: &http.Client{
			Timeout:   30 * time.Second,
			Transport: transport,
		},
	}, nil
}

// authHeaders returns X-Agent-Token header if token is configured
func (c *ControlPlaneClient) authHeaders(req *http.Request) {
	if c.config.AgentToken != "" {
		req.Header.Set("X-Agent-Token", c.config.AgentToken)
	}
}

// Register submits TOFU registration
func (c *ControlPlaneClient) Register(fingerprint string) (*RegisterResponse, error) {
	reqBody := RegisterRequest{
		Name:        c.config.AgentName,
		Fingerprint: fingerprint,
	}

	jsonBody, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	url := fmt.Sprintf("%s/api/agent/register", c.baseURL)
	req, err := http.NewRequest("POST", url, bytes.NewReader(jsonBody))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("registration failed: %s - %s", resp.Status, string(body))
	}

	var result RegisterResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// CheckRegistrationStatus polls the approval status
func (c *ControlPlaneClient) CheckRegistrationStatus(agentID, fingerprint string) (*RegisterStatusResponse, error) {
	u := fmt.Sprintf("%s/api/agent/register/status?agent_id=%s&fingerprint=%s",
		c.baseURL,
		url.QueryEscape(agentID),
		url.QueryEscape(fingerprint),
	)

	resp, err := c.httpClient.Get(u)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("status check failed: %s - %s", resp.Status, string(body))
	}

	var result RegisterStatusResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// Heartbeat sends a heartbeat to the control plane
func (c *ControlPlaneClient) Heartbeat() (*HeartbeatResponse, error) {
	reqBody := HeartbeatRequest{Status: "ok"}

	jsonBody, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	reqURL := fmt.Sprintf("%s/api/agent/heartbeat", c.baseURL)
	req, err := http.NewRequest("POST", reqURL, bytes.NewReader(jsonBody))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	c.authHeaders(req)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("heartbeat failed: %s - %s", resp.Status, string(body))
	}

	var result HeartbeatResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// FetchCerts sends a batch cert check request
func (c *ControlPlaneClient) FetchCerts(checks []CertCheckItem) (*FetchCertsResponse, error) {
	reqBody := FetchCertsRequest{Certs: checks}

	jsonBody, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	reqURL := fmt.Sprintf("%s/api/agent/fetch-certs", c.baseURL)
	req, err := http.NewRequest("POST", reqURL, bytes.NewReader(jsonBody))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	c.authHeaders(req)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("fetch-certs failed: %s - %s", resp.Status, string(body))
	}

	var result FetchCertsResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// ReportCerts reports deployed certificates to the control plane
func (c *ControlPlaneClient) ReportCerts(certs []ReportCertItem) (*ReportCertsResponse, error) {
	reqBody := ReportCertsRequest{Certs: certs}

	jsonBody, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	reqURL := fmt.Sprintf("%s/api/agent/report-certs", c.baseURL)
	req, err := http.NewRequest("POST", reqURL, bytes.NewReader(jsonBody))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	c.authHeaders(req)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("report-certs failed: %s - %s", resp.Status, string(body))
	}

	var result ReportCertsResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &result, nil
}

// ComputeFingerprint computes SHA256 of the DER-encoded public key from a PEM private key file
func ComputeFingerprint(keyPEM []byte) (string, error) {
	block, _ := pem.Decode(keyPEM)
	if block == nil {
		return "", fmt.Errorf("failed to decode PEM block")
	}

	key, err := x509.ParsePKCS1PrivateKey(block.Bytes)
	if err != nil {
		// Try PKCS8
		keyAny, err2 := x509.ParsePKCS8PrivateKey(block.Bytes)
		if err2 != nil {
			return "", fmt.Errorf("failed to parse private key: %w (pkcs1: %v)", err2, err)
		}
		pubDER, err2 := x509.MarshalPKIXPublicKey(keyAny.(*interface{}))
		if err2 != nil {
			return "", fmt.Errorf("failed to marshal public key: %w", err2)
		}
		sum := sha256.Sum256(pubDER)
		return fmt.Sprintf("%x", sum), nil
	}

	pubDER, err := x509.MarshalPKIXPublicKey(&key.PublicKey)
	if err != nil {
		return "", fmt.Errorf("failed to marshal public key: %w", err)
	}
	sum := sha256.Sum256(pubDER)
	return fmt.Sprintf("%x", sum), nil
}
