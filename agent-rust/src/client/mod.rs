use anyhow::{Context, Result};
use reqwest::{Client, ClientBuilder};
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tracing::{debug, info};

use crate::config::AgentConfig;

// ── Request / Response types ─────────────────────────────────────────────────

/// TOFU registration request: agent sends its name and public-key fingerprint
#[derive(Debug, Serialize)]
pub struct RegisterRequest {
    pub name: String,
    /// SHA-256 of the DER-encoded SubjectPublicKeyInfo, hex-encoded
    pub fingerprint: String,
}

/// Server response to a registration attempt
#[derive(Debug, Deserialize)]
pub struct RegisterResponse {
    /// "pending" | "approved"
    pub status: String,
    pub agent_id: String,
    /// Present only when status == "approved"
    pub agent_token: Option<String>,
    pub message: String,
}

/// Server response when polling registration status
#[derive(Debug, Deserialize)]
pub struct RegisterStatusResponse {
    pub status: String,
    pub agent_token: Option<String>,
    pub message: String,
}

/// One entry in the batch cert-check request
#[derive(Debug, Serialize)]
pub struct CertCheckItem {
    pub local_path: String,
    /// RFC-3339 not_after of the locally installed cert; null if no cert yet
    #[serde(skip_serializing_if = "Option::is_none")]
    pub current_not_after: Option<String>,
}

/// One entry in the batch cert-check response
#[derive(Debug, Deserialize)]
pub struct CertUpdateItem {
    pub local_path: String,
    pub has_update: bool,
    pub cert_pem: Option<String>,
    /// Plaintext private key (decrypted by server)
    pub key_pem: Option<String>,
    pub chain_pem: Option<String>,
    pub not_after: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct FetchCertsRequest {
    pub certs: Vec<CertCheckItem>,
}

#[derive(Debug, Deserialize)]
pub struct FetchCertsResponse {
    pub updates: Vec<CertUpdateItem>,
}

#[derive(Debug, Serialize)]
pub struct HeartbeatRequest {
    pub status: String,
}

#[derive(Debug, Deserialize)]
pub struct HeartbeatResponse {
    pub acknowledged: bool,
    pub pending_action: Option<String>,
}

// ── Client ───────────────────────────────────────────────────────────────────

pub struct ControlPlaneClient {
    client: Client,
    base_url: String,
    agent_token: Option<String>,
}

impl ControlPlaneClient {
    /// Create a plain HTTP client (no mTLS, no token) – used during registration
    pub fn new(config: &AgentConfig) -> Result<Self> {
        let client = ClientBuilder::new()
            .timeout(Duration::from_secs(30))
            .build()
            .context("Failed to build HTTP client")?;

        Ok(Self {
            client,
            base_url: config.cp_url.clone(),
            agent_token: None,
        })
    }

    /// Create a client that injects `X-Agent-Token` on every request
    pub fn with_token(config: &AgentConfig, token: String) -> Result<Self> {
        let client = ClientBuilder::new()
            .timeout(Duration::from_secs(30))
            .build()
            .context("Failed to build HTTP client")?;

        Ok(Self {
            client,
            base_url: config.cp_url.clone(),
            agent_token: Some(token),
        })
    }

    /// TOFU registration: send name + fingerprint
    pub async fn register(&self, name: &str, fingerprint: &str) -> Result<RegisterResponse> {
        let url = format!("{}/api/agent/register", self.base_url);
        debug!("Sending TOFU registration to {}", url);

        let req = RegisterRequest {
            name: name.to_string(),
            fingerprint: fingerprint.to_string(),
        };

        let resp = self.client.post(&url).json(&req).send().await
            .context("Failed to send registration request")?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            anyhow::bail!("Registration failed: {} – {}", status, body);
        }

        let result: RegisterResponse = resp.json().await
            .context("Failed to parse registration response")?;

        info!("Registered agent_id={}, status={}", result.agent_id, result.status);
        Ok(result)
    }

    /// Poll registration status while waiting for admin approval
    pub async fn check_registration_status(
        &self,
        agent_id: &str,
        fingerprint: &str,
    ) -> Result<RegisterStatusResponse> {
        let url = format!(
            "{}/api/agent/register/status?agent_id={}&fingerprint={}",
            self.base_url, agent_id, fingerprint
        );

        let resp = self.client.get(&url).send().await
            .context("Failed to poll registration status")?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            anyhow::bail!("Status poll failed: {} – {}", status, body);
        }

        let result: RegisterStatusResponse = resp.json().await
            .context("Failed to parse status response")?;
        Ok(result)
    }

    /// Send a heartbeat; requires agent_token
    pub async fn heartbeat(&self) -> Result<HeartbeatResponse> {
        let url = format!("{}/api/agent/heartbeat", self.base_url);

        let req = HeartbeatRequest { status: "ok".to_string() };

        let mut builder = self.client.post(&url).json(&req);
        if let Some(tok) = &self.agent_token {
            builder = builder.header("X-Agent-Token", tok);
        }

        let resp = builder.send().await.context("Failed to send heartbeat")?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            anyhow::bail!("Heartbeat failed: {} – {}", status, body);
        }

        let result: HeartbeatResponse = resp.json().await
            .context("Failed to parse heartbeat response")?;
        Ok(result)
    }

    /// Batch fetch-certs; requires agent_token
    pub async fn fetch_certs(&self, items: Vec<CertCheckItem>) -> Result<FetchCertsResponse> {
        let url = format!("{}/api/agent/fetch-certs", self.base_url);

        let req = FetchCertsRequest { certs: items };

        let mut builder = self.client.post(&url).json(&req);
        if let Some(tok) = &self.agent_token {
            builder = builder.header("X-Agent-Token", tok);
        }

        let resp = builder.send().await.context("Failed to send fetch-certs request")?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            anyhow::bail!("fetch-certs failed: {} – {}", status, body);
        }

        let result: FetchCertsResponse = resp.json().await
            .context("Failed to parse fetch-certs response")?;
        Ok(result)
    }
}
