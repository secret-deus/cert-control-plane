use anyhow::{Context, Result};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Duration;
use tokio::time::sleep;
use tracing::{debug, error, info, warn};

use crate::client::{CertCheckItem, CertUpdateItem, ControlPlaneClient};
use crate::config::AgentConfig;
use crate::crypto;

/// Agent runner: handles TOFU registration and the main cert-sync loop
pub struct Runner {
    config: AgentConfig,
}

impl Runner {
    pub fn new(config: AgentConfig) -> Self {
        Self { config }
    }

    /// Entry point: register if needed, then run the heartbeat + cert-sync loop
    pub async fn run(mut self) -> Result<()> {
        info!(name = %self.config.name, cp_url = %self.config.cp_url, "cert-agent starting");

        // Ensure state directory exists
        fs::create_dir_all(&self.config.state_dir)
            .with_context(|| format!("Failed to create state dir {:?}", self.config.state_dir))?;

        // Load or generate RSA identity key
        let key = if self.config.key_path().exists() {
            info!("Loading existing identity key from {:?}", self.config.key_path());
            crypto::load_private_key(&self.config.key_path())?
        } else {
            info!("Generating new identity key");
            let k = crypto::generate_key_pair().context("Failed to generate key pair")?;
            crypto::save_private_key(&k, &self.config.key_path())?;
            k
        };

        let fingerprint = crypto::compute_fingerprint(&key)
            .context("Failed to compute fingerprint")?;
        info!(fingerprint = %fingerprint, "Identity key ready");

        // Obtain agent token (from file or via TOFU registration)
        let agent_token = if self.config.is_registered() {
            info!("Loading persisted agent token");
            fs::read_to_string(self.config.agent_token_path())
                .context("Failed to read agent token file")?
                .trim()
                .to_string()
        } else {
            self.tofu_register(&fingerprint).await?
        };

        // Persist the token into config for convenience
        self.config.agent_token = agent_token.clone();

        // Build an authenticated client
        let client = ControlPlaneClient::with_token(&self.config, agent_token)
            .context("Failed to create authenticated client")?;

        self.main_loop(client).await
    }

    // ── TOFU registration ────────────────────────────────────────────────────

    /// Perform TOFU registration and poll until the admin approves.
    /// Returns the agent_token.
    async fn tofu_register(&self, fingerprint: &str) -> Result<String> {
        let client = ControlPlaneClient::new(&self.config)
            .context("Failed to create registration client")?;

        info!("Sending TOFU registration request");
        let resp = client
            .register(&self.config.name, fingerprint)
            .await
            .context("Registration request failed")?;

        let agent_id = resp.agent_id.clone();

        // If already approved in one shot (e.g. re-registration with same fingerprint)
        if resp.status == "approved" {
            let token = resp
                .agent_token
                .ok_or_else(|| anyhow::anyhow!("Approved but no agent_token in response"))?;
            self.save_agent_token(&token)?;
            return Ok(token);
        }

        info!(
            agent_id = %agent_id,
            "Registration pending – waiting for admin approval"
        );

        // Poll until approved or rejected
        loop {
            sleep(Duration::from_secs(self.config.poll_interval)).await;

            let status = client
                .check_registration_status(&agent_id, fingerprint)
                .await
                .context("Failed to poll registration status")?;

            match status.status.as_str() {
                "approved" => {
                    let token = status.agent_token.ok_or_else(|| {
                        anyhow::anyhow!("Approved but no agent_token in status response")
                    })?;
                    info!("Registration approved");
                    self.save_agent_token(&token)?;
                    return Ok(token);
                }
                "rejected" | "revoked" => {
                    anyhow::bail!("Registration was rejected by the administrator");
                }
                _ => {
                    debug!("Still pending approval…");
                }
            }
        }
    }

    fn save_agent_token(&self, token: &str) -> Result<()> {
        let path = self.config.agent_token_path();
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(&path, token).context("Failed to save agent token")?;
        info!("Agent token saved to {:?}", path);
        Ok(())
    }

    // ── Main loop ────────────────────────────────────────────────────────────

    async fn main_loop(&self, client: ControlPlaneClient) -> Result<()> {
        let interval = Duration::from_secs(self.config.heartbeat_interval);
        info!(interval_secs = ?interval, "Entering main loop");

        loop {
            // Heartbeat
            match client.heartbeat().await {
                Ok(_) => debug!("Heartbeat OK"),
                Err(e) => error!("Heartbeat failed: {:#}", e),
            }

            // Cert sync
            if !self.config.cert_table.is_empty() {
                if let Err(e) = self.sync_certs(&client).await {
                    error!("Cert sync failed: {:#}", e);
                }
            }

            sleep(interval).await;
        }
    }

    /// Build the check-items list, call fetch-certs, and deploy any updates
    async fn sync_certs(&self, client: &ControlPlaneClient) -> Result<()> {
        let check_items: Vec<CertCheckItem> = self
            .config
            .cert_table
            .iter()
            .map(|entry| {
                let path = PathBuf::from(&entry.local_path);
                let current_not_after = crypto::read_cert_not_after(&path);
                debug!(
                    path = %entry.local_path,
                    not_after = ?current_not_after,
                    "Checking cert"
                );
                CertCheckItem {
                    local_path: entry.local_path.clone(),
                    current_not_after,
                }
            })
            .collect();

        let response = client
            .fetch_certs(check_items)
            .await
            .context("fetch-certs request failed")?;

        let mut deployed = 0usize;
        for update in &response.updates {
            if update.has_update {
                match self.deploy_cert(update).await {
                    Ok(()) => deployed += 1,
                    Err(e) => error!(path = %update.local_path, "Deploy failed: {:#}", e),
                }
            }
        }

        if deployed > 0 {
            info!(count = deployed, "Certs deployed; reloading service");
            self.reload_service();
        }

        Ok(())
    }

    /// Write cert, key, and chain to the appropriate paths
    async fn deploy_cert(&self, update: &CertUpdateItem) -> Result<()> {
        let cert_path = PathBuf::from(&update.local_path);
        let key_path = cert_path.with_extension("key");
        let chain_path = derive_chain_path(&cert_path);

        if let Some(cert_pem) = &update.cert_pem {
            let fullchain = fullchain_pem(cert_pem, update.chain_pem.as_deref());
            crypto::save_certificate(&fullchain, &cert_path)
                .with_context(|| format!("Failed to write cert to {:?}", cert_path))?;
        }

        if let Some(key_pem) = &update.key_pem {
            save_key_secure(key_pem, &key_path)
                .with_context(|| format!("Failed to write key to {:?}", key_path))?;
        }

        if chain_path.exists() {
            fs::remove_file(&chain_path)
                .with_context(|| format!("Failed to remove chain sidecar {:?}", chain_path))?;
        }

        info!(path = %update.local_path, not_after = ?update.not_after, "Cert deployed");
        Ok(())
    }

    /// Run the configured reload command, logging failures as warnings
    fn reload_service(&self) {
        if self.config.reload_cmd.is_empty() {
            return;
        }
        match Command::new("sh")
            .arg("-c")
            .arg(&self.config.reload_cmd)
            .output()
        {
            Ok(output) if output.status.success() => {
                info!("Service reloaded successfully");
            }
            Ok(output) => {
                let stderr = String::from_utf8_lossy(&output.stderr);
                warn!("Reload command returned non-zero: {}", stderr);
            }
            Err(e) => {
                warn!("Failed to execute reload command: {}", e);
            }
        }
    }
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/// Derive chain path from cert path: foo.crt → foo.chain.crt
fn derive_chain_path(cert_path: &Path) -> PathBuf {
    let stem = cert_path
        .file_stem()
        .unwrap_or_default()
        .to_string_lossy();
    let parent = cert_path.parent().unwrap_or_else(|| Path::new("."));
    parent.join(format!("{}.chain.crt", stem))
}

fn fullchain_pem(cert_pem: &str, chain_pem: Option<&str>) -> String {
    let mut fullchain = format!("{}\n", cert_pem.trim());
    if let Some(chain) = chain_pem {
        fullchain.push_str(chain.trim());
        fullchain.push('\n');
    }
    fullchain
}

/// Save a private key with 0600 permissions on Unix
fn save_key_secure(key_pem: &str, path: &Path) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }

    #[cfg(unix)]
    {
        use std::io::Write;
        use std::os::unix::fs::OpenOptionsExt;
        let mut file = fs::OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .mode(0o600)
            .open(path)
            .with_context(|| format!("Failed to open {:?}", path))?;
        file.write_all(key_pem.as_bytes())
            .context("Failed to write key")?;
    }
    #[cfg(not(unix))]
    {
        fs::write(path, key_pem).with_context(|| format!("Failed to write key to {:?}", path))?;
    }

    Ok(())
}
