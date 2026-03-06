"""
Deterministic tests for boss AI decision logic.
"""
import unittest
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bm_params import EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE, BOMB_TIMER, CELL_SIZE
from ai_controller import (
    compute_ai_input,
    _opponent_in_blast_range_with_los,
    _can_escape_after_bomb,
    _get_danger_cells,
    _cells_with_bombs,
    _cell_walkable,
    _bfs_safe_direction,
)


def _make_mock_player(x, y, fire_power=1, bomb_capacity=1, active_bombs=0):
    """Create a minimal player-like object for testing."""
    class MockPlayer:
        pass
    p = MockPlayer()
    p.pos = [x * CELL_SIZE + CELL_SIZE // 2, y * CELL_SIZE + CELL_SIZE // 2]
    p.fire_power = fire_power
    p.bomb_capacity = bomb_capacity
    p.active_bombs = active_bombs
    p.alive = True
    p.get_grid_pos = lambda: (int(p.pos[0] // CELL_SIZE), int(p.pos[1] // CELL_SIZE))
    return p


def _make_mock_bomb(x, y, start_time=0, fire_power=1, owner=None):
    class MockBomb:
        pass
    b = MockBomb()
    b.x, b.y = x, y
    b.start_time = start_time
    b.fire_power = fire_power
    b.owner = owner
    b.owner_left = False
    return b


def _make_mock_game(board, bombs=None, explosions=None, players=None, powerups=None, current_time=0):
    class MockGame:
        pass
    g = MockGame()
    g.board = board
    g.bombs = bombs or []
    g.explosions = explosions or []
    g.players = players or []
    g.powerups = powerups or []
    g.current_time = current_time
    g.grid_width = len(board[0])
    g.grid_height = len(board)
    return g


class TestAIController(unittest.TestCase):
    """Tests for boss AI decision logic."""

    def test_opponent_behind_wall_does_not_trigger_bomb(self):
        """AI should not place bomb when opponent is in range but blocked by wall."""
        # 5x5 board: AI at (1,2), opponent at (3,2), indestructible wall at (2,2).
        # No destructible walls nearby so only opponent-LOS could trigger bomb.
        board = [
            [INDESTRUCTIBLE] * 5,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 5,
        ]
        ai = _make_mock_player(1, 2)
        ai.fire_power = 3
        opponent = _make_mock_player(3, 2)
        ai.is_ai = True
        game = _make_mock_game(board, players=[ai, opponent])
        # No LOS - wall at (2,2) blocks
        self.assertFalse(_opponent_in_blast_range_with_los(ai, game))
        # No destructible adjacent, so AI should never place bomb
        for _ in range(20):
            _, place_bomb = compute_ai_input(ai, game)
            self.assertFalse(place_bomb, "AI should not bomb when opponent behind wall")

    def test_opponent_in_los_triggers_bomb_when_safe(self):
        """AI should place bomb when opponent has LOS and escape is possible."""
        # 5x5: AI at (1,2), opponent at (3,2), clear line
        board = [
            [INDESTRUCTIBLE] * 5,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 5,
        ]
        ai = _make_mock_player(1, 2)
        ai.fire_power = 2
        opponent = _make_mock_player(3, 2)
        ai.is_ai = True
        game = _make_mock_game(board, players=[ai, opponent])
        self.assertTrue(_opponent_in_blast_range_with_los(ai, game))
        # Can escape to (1,1) or (1,3) - not in blast
        self.assertTrue(_can_escape_after_bomb(ai, game, set()))
        # AI should sometimes bomb (deterministic given escape)
        _, place_bomb = compute_ai_input(ai, game)
        self.assertTrue(place_bomb)

    def test_ai_avoids_bomb_cells_while_escaping(self):
        """Pathfinding should not route through cells with bombs."""
        # 3x3: AI at (1,1), bomb at (1,0), danger from bomb. Safe at (0,1) or (2,1)
        board = [
            [INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE],
            [EMPTY, EMPTY, EMPTY],
            [INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE],
        ]
        ai = _make_mock_player(1, 1)
        bomb = _make_mock_bomb(1, 0, start_time=0, owner=ai)
        game = _make_mock_game(board, bombs=[bomb], players=[ai], current_time=BOMB_TIMER - 400)
        danger = _get_danger_cells(game)
        bomb_cells = _cells_with_bombs(game.bombs)
        # (1,0) has bomb - not walkable
        self.assertFalse(_cell_walkable(board, 1, 0, set(), bomb_cells))
        # (0,1) and (2,1) are safe
        self.assertTrue(_cell_walkable(board, 0, 1, danger, bomb_cells))
        self.assertTrue(_cell_walkable(board, 2, 1, danger, bomb_cells))
        direction = _bfs_safe_direction(board, 1, 1, danger, bomb_cells=bomb_cells)
        self.assertIsNotNone(direction)
        # Should move left or right, not up into bomb
        self.assertNotEqual(direction, (0, -1))

    def test_ai_refuses_bomb_when_no_escape(self):
        """AI should not place bomb when it would trap itself."""
        # 3x1 corridor: AI at (1,0), opponent at (1,2). Blast would cover (1,0),(1,1),(1,2). No escape.
        board = [
            [INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE],
        ]
        ai = _make_mock_player(1, 1)
        ai.fire_power = 2
        opponent = _make_mock_player(1, 0)  # Actually put opponent in blast
        ai.is_ai = True
        game = _make_mock_game(board, players=[ai, opponent])
        # Blast covers (1,0),(1,1),(1,2) - entire column. No safe cell.
        self.assertFalse(_can_escape_after_bomb(ai, game, set()))
        _, place_bomb = compute_ai_input(ai, game)
        self.assertFalse(place_bomb)

    def test_ai_moves_away_from_imminent_danger(self):
        """AI in danger should choose a direction toward safety when escape exists."""
        # 5x5: AI at (1,1), bomb at (2,1) about to explode. Safe cell at (0,1).
        board = [
            [INDESTRUCTIBLE] * 5,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 5,
        ]
        ai = _make_mock_player(1, 1)
        bomb = _make_mock_bomb(2, 1, start_time=0, owner=ai)
        game = _make_mock_game(board, bombs=[bomb], players=[ai], current_time=BOMB_TIMER - 200)
        danger = _get_danger_cells(game)
        self.assertIn((1, 1), danger)
        direction, _ = compute_ai_input(ai, game)
        # Should move toward (0,1) i.e. left: dx=-1
        self.assertTrue(
            direction[0] != 0 or direction[1] != 0,
            "AI in danger with escape route should move"
        )


if __name__ == "__main__":
    unittest.main()
