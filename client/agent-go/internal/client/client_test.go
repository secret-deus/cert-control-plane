package client

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"testing"
)

func TestComputeFingerprintSupportsPKCS8RSAKeys(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}

	der, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		t.Fatalf("marshal pkcs8: %v", err)
	}
	pemBytes := pem.EncodeToMemory(&pem.Block{
		Type:  "PRIVATE KEY",
		Bytes: der,
	})

	pubDER, err := x509.MarshalPKIXPublicKey(&key.PublicKey)
	if err != nil {
		t.Fatalf("marshal public key: %v", err)
	}
	expected := fmt.Sprintf("%x", sha256.Sum256(pubDER))

	actual, err := ComputeFingerprint(pemBytes)
	if err != nil {
		t.Fatalf("compute fingerprint: %v", err)
	}
	if actual != expected {
		t.Fatalf("fingerprint mismatch: got %s want %s", actual, expected)
	}
}

func TestComputeFingerprintRejectsNonRSAKeys(t *testing.T) {
	block := pem.EncodeToMemory(&pem.Block{
		Type:  "PRIVATE KEY",
		Bytes: []byte("not a private key"),
	})

	if _, err := ComputeFingerprint(block); err == nil {
		t.Fatal("expected error for invalid private key")
	}
}
