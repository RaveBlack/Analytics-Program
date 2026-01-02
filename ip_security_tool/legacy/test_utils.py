import unittest
import os
from utils import validate_and_check_ip, mask_email, load_or_generate_key, encrypt_data, decrypt_data, KEY_FILE

class TestSecurityTool(unittest.TestCase):
    def setUp(self):
        # Ensure we don't overwrite an existing key if this runs in prod (though here it is dev)
        # For testing, we can back it up or just generate a new one if missing
        self.key = load_or_generate_key()

    def test_validate_ip(self):
        valid, public, _ = validate_and_check_ip("8.8.8.8")
        self.assertTrue(valid)
        self.assertTrue(public)
        
        valid, public, _ = validate_and_check_ip("192.168.1.1")
        self.assertTrue(valid)
        self.assertFalse(public)
        
        valid, _, _ = validate_and_check_ip("999.999.999.999")
        self.assertFalse(valid)

    def test_mask_email(self):
        valid, masked = mask_email("user@example.com")
        self.assertTrue(valid)
        self.assertEqual(masked, "u***r@example.com")

    def test_encryption_decryption(self):
        original_text = "SecretPassword123!"
        encrypted = encrypt_data(original_text, self.key)
        
        self.assertNotEqual(original_text, encrypted)
        
        success, decrypted = decrypt_data(encrypted, self.key)
        self.assertTrue(success)
        self.assertEqual(original_text, decrypted)

    def test_decryption_fail(self):
        success, _ = decrypt_data("InvalidEncryptedString", self.key)
        self.assertFalse(success)

if __name__ == "__main__":
    unittest.main()
