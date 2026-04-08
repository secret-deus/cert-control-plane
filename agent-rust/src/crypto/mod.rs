use anyhow::{Context, Result};
use rsa::{RsaPrivateKey, RsaPublicKey};
use rsa::pkcs8::{EncodePrivateKey, LineEnding};
use sha2::{Sha256, Digest};
use spki::EncodePublicKey;
use pkcs8::DecodePrivateKey;
use rand::rngs::OsRng;
use std::fs;
use std::path::Path;
use x509_cert::der::Decode;

/// Generate a new RSA key pair (2048 bits)
pub fn generate_key_pair() -> Result<RsaPrivateKey> {
    let mut rng = OsRng;
    let private_key = RsaPrivateKey::new(&mut rng, 2048)
        .context("Failed to generate RSA key")?;
    Ok(private_key)
}

/// Compute fingerprint: SHA256(DER-encoded SubjectPublicKeyInfo) as hex string
pub fn compute_fingerprint(private_key: &RsaPrivateKey) -> Result<String> {
    let public_key = RsaPublicKey::from(private_key);
    let der = public_key
        .to_public_key_der()
        .context("Failed to encode public key as DER")?;
    let mut hasher = Sha256::new();
    hasher.update(der.as_bytes());
    let hash = hasher.finalize();
    Ok(hex::encode(hash))
}

/// Save private key to file with restricted permissions (0600)
pub fn save_private_key(key: &RsaPrivateKey, path: &Path) -> Result<()> {
    let pem = key
        .to_pkcs8_pem(LineEnding::LF)
        .context("Failed to encode private key as PEM")?;

    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("Failed to create directory {:?}", parent))?;
    }

    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        let mut file = fs::OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .mode(0o600)
            .open(path)
            .with_context(|| format!("Failed to open {:?} for writing", path))?;
        std::io::Write::write_all(&mut file, pem.as_bytes())
            .context("Failed to write private key")?;
    }
    #[cfg(not(unix))]
    {
        fs::write(path, pem.as_bytes())
            .with_context(|| format!("Failed to write key to {:?}", path))?;
    }

    Ok(())
}

/// Load private key from file
pub fn load_private_key(path: &Path) -> Result<RsaPrivateKey> {
    let pem = fs::read_to_string(path)
        .with_context(|| format!("Failed to read key from {:?}", path))?;
    RsaPrivateKey::from_pkcs8_pem(&pem).context("Failed to parse private key")
}

/// Save certificate PEM to file (creates parent directories if needed)
pub fn save_certificate(cert_pem: &str, path: &Path) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("Failed to create directory {:?}", parent))?;
    }
    fs::write(path, cert_pem)
        .with_context(|| format!("Failed to write certificate to {:?}", path))?;
    Ok(())
}

/// Read the not_after datetime from a PEM certificate file.
/// Returns None if the file doesn't exist or cannot be parsed.
pub fn read_cert_not_after(path: &Path) -> Option<String> {
    if !path.exists() {
        return None;
    }

    let pem_data = fs::read(path).ok()?;
    let (_label, der_bytes) = pem_rfc7468::decode_vec(&pem_data).ok()?;
    let cert = x509_cert::Certificate::from_der(&der_bytes).ok()?;

    let not_after = cert.tbs_certificate.validity.not_after;

    let unix_secs: i64 = match not_after {
        x509_cert::der::asn1::Time::UtcTime(t) => {
            t.to_date_time().unix_duration().as_secs() as i64
        }
        x509_cert::der::asn1::Time::GeneralizedTime(t) => {
            t.to_date_time().unix_duration().as_secs() as i64
        }
    };

    use chrono::TimeZone;
    let dt = chrono::Utc.timestamp_opt(unix_secs, 0).single()?;
    Some(dt.to_rfc3339())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_generate_key_pair() {
        let key = generate_key_pair().unwrap();
        assert_eq!(key.size(), 2048 / 8);
    }

    #[test]
    fn test_compute_fingerprint() {
        let key = generate_key_pair().unwrap();
        let fp = compute_fingerprint(&key).unwrap();
        assert_eq!(fp.len(), 64); // SHA256 hex = 64 chars
    }

    #[test]
    fn test_save_and_load_private_key() {
        let temp_dir = TempDir::new().unwrap();
        let key_path = temp_dir.path().join("test.key");

        let key = generate_key_pair().unwrap();
        save_private_key(&key, &key_path).unwrap();

        let loaded = load_private_key(&key_path).unwrap();
        assert_eq!(key.n(), loaded.n());
    }
}
