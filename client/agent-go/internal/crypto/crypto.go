package crypto

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"fmt"
	"os"
)

// GenerateKeyPair generates a new RSA key pair
func GenerateKeyPair(bits int) (*rsa.PrivateKey, error) {
	return rsa.GenerateKey(rand.Reader, bits)
}

// GenerateCSR generates a Certificate Signing Request
func GenerateCSR(key *rsa.PrivateKey, commonName string, sans []string) ([]byte, error) {
	template := x509.CertificateRequest{
		Subject: pkix.Name{
			CommonName: commonName,
		},
	}

	// Add SANs if provided
	if len(sans) > 0 {
		template.DNSNames = make([]string, 0, len(sans))
		template.IPAddresses = make([]string, 0, len(sans))
		for _, san := range sans {
			// Simple heuristic: if it contains dots and letters, it's a DNS name
			// otherwise treat as IP (simplified)
			template.DNSNames = append(template.DNSNames, san)
		}
	}

	csrDER, err := x509.CreateCertificateRequest(rand.Reader, &template, key)
	if err != nil {
		return nil, fmt.Errorf("failed to create CSR: %w", err)
	}

	csrPEM := pem.EncodeToMemory(&pem.Block{
		Type:  "CERTIFICATE REQUEST",
		Bytes: csrDER,
	})

	return csrPEM, nil
}

// SavePrivateKey saves a private key to file with restricted permissions
func SavePrivateKey(key *rsa.PrivateKey, path string) error {
	keyDER := x509.MarshalPKCS1PrivateKey(key)
	keyPEM := pem.EncodeToMemory(&pem.Block{
		Type:  "RSA PRIVATE KEY",
		Bytes: keyDER,
	})

	// Write with restricted permissions (0600)
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0600)
	if err != nil {
		return fmt.Errorf("failed to create key file: %w", err)
	}
	defer file.Close()

	if _, err := file.Write(keyPEM); err != nil {
		return fmt.Errorf("failed to write key: %w", err)
	}

	return nil
}

// LoadPrivateKey loads a private key from file
func LoadPrivateKey(path string) (*rsa.PrivateKey, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("failed to read key file: %w", err)
	}

	block, _ := pem.Decode(data)
	if block == nil {
		return nil, fmt.Errorf("failed to decode PEM block")
	}

	key, err := x509.ParsePKCS1PrivateKey(block.Bytes)
	if err != nil {
		// Try PKCS8
		keyInterface, err := x509.ParsePKCS8PrivateKey(block.Bytes)
		if err != nil {
			return nil, fmt.Errorf("failed to parse private key: %w", err)
		}
		var ok bool
		key, ok = keyInterface.(*rsa.PrivateKey)
		if !ok {
			return nil, fmt.Errorf("key is not RSA")
		}
	}

	return key, nil
}

// SaveCertificate saves a certificate to file
func SaveCertificate(certPEM []byte, path string) error {
	return os.WriteFile(path, certPEM, 0644)
}

// LoadCertificate loads a certificate from file
func LoadCertificate(path string) (*x509.Certificate, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("failed to read cert file: %w", err)
	}

	block, _ := pem.Decode(data)
	if block == nil {
		return nil, fmt.Errorf("failed to decode PEM block")
	}

	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("failed to parse certificate: %w", err)
	}

	return cert, nil
}

// ParseCertificate parses a certificate from PEM bytes
func ParseCertificate(certPEM []byte) (*x509.Certificate, error) {
	block, _ := pem.Decode(certPEM)
	if block == nil {
		return nil, fmt.Errorf("failed to decode PEM block")
	}

	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("failed to parse certificate: %w", err)
	}

	return cert, nil
}

// CalculateFingerprint calculates SHA-256 fingerprint of certificate
func CalculateFingerprint(cert *x509.Certificate) string {
	return fmt.Sprintf("%x", cert.Fingerprint)
}

// ExtractSerialNumber extracts the serial number from a certificate PEM
func ExtractSerialNumber(certPEM []byte) (string, error) {
	cert, err := ParseCertificate(certPEM)
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("%x", cert.SerialNumber), nil
}
