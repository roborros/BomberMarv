import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from input_abstraction import (
    InputManager,
    KeyboardInputBackend,
    Keys,
    get_key_name,
    is_key_pressed,
    set_input_backend,
)


class InputAbstractionTests(unittest.TestCase):
    def tearDown(self):
        from input_abstraction import PygameInputBackend, set_input_backend

        set_input_backend(PygameInputBackend())

    def test_letter_constants_are_distinct(self):
        self.assertNotEqual(Keys.W, Keys.S)
        self.assertEqual(Keys.ENTER, Keys.RETURN)

    def test_keyboard_backend_is_inert(self):
        backend = KeyboardInputBackend()
        self.assertEqual(backend.get_pressed_keys(), {})
        self.assertFalse(backend.is_key_pressed(Keys.W))
        self.assertTrue(backend.get_key_name(12).startswith("key_"))
        backend.cleanup()

    def test_manager_can_switch_backend(self):
        manager = InputManager(KeyboardInputBackend())
        self.assertFalse(manager.is_key_pressed(Keys.A))
        self.assertEqual(manager.get_pressed_keys(), {})

    def test_global_backend_switch(self):
        set_input_backend(KeyboardInputBackend())
        self.assertFalse(is_key_pressed(Keys.SPACE))
        self.assertTrue(isinstance(get_key_name(1), str))


if __name__ == "__main__":
    unittest.main()
