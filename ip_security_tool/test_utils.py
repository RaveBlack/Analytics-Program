import unittest
from utils import validate_and_check_ip, mask_email, hash_password

class TestSecurityTool(unittest.TestCase):
    def test_validate_ip(self):
        # Public IP (Google DNS)
        valid, public, _ = validate_and_check_ip("8.8.8.8")
        self.assertTrue(valid)
        self.assertTrue(public)
        
        # Private IP
        valid, public, _ = validate_and_check_ip("192.168.1.1")
        self.assertTrue(valid)
        self.assertFalse(public)
        
        # Invalid IP
        valid, _, _ = validate_and_check_ip("999.999.999.999")
        self.assertFalse(valid)

    def test_mask_email(self):
        valid, masked = mask_email("user@example.com")
        self.assertTrue(valid)
        self.assertEqual(masked, "u***r@example.com")
        
        valid, masked = mask_email("a@b.com")
        self.assertTrue(valid)
        self.assertEqual(masked, "*@b.com")

        valid, masked = mask_email("invalid-email")
        self.assertFalse(valid)

    def test_hash_password(self):
        # SHA-256 for "test"
        # echo -n "test" | sha256sum
        expected = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
        self.assertEqual(hash_password("test"), expected)

if __name__ == "__main__":
    unittest.main()
