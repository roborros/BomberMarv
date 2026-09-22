"""
Deterministic tests for boss AI decision logic.
"""
import unittest
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bm_params import EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE, BOMB_TIMER, CELL_SIZE, EXPLOSION_DURATION
from ai_controller import (
    compute_ai_input,
    think_ai,
    _opponent_in_blast_range_with_los,
    _can_escape_after_bomb,
    _get_danger_cells,
    _cells_with_bombs,
    _cell_walkable,
    _bfs_safe_direction,
    _align_then_turn,
    _is_cell_centered,
    _danger_times,
    _nearest_powerup,
    AI_THINK_INTERVAL_MS,
    AI_STICKY_MS,
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

    def test_bfs_from_safe_cell_does_not_walk_through_danger(self):
        board = [
            [INDESTRUCTIBLE] * 5,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 5,
        ]
        danger = {(2, 1), (2, 2), (2, 3)}
        direction = _bfs_safe_direction(board, 1, 1, danger, bomb_cells=set())
        self.assertEqual(direction, (0, 0))

    def test_explosion_cells_stop_at_indestructible(self):
        board = [
            [INDESTRUCTIBLE] * 5,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 5,
        ]
        from ai_controller import _explosion_cells_for_bomb

        bomb = _make_mock_bomb(1, 2, fire_power=3)
        game = _make_mock_game(board)
        cells = _explosion_cells_for_bomb(bomb, game)
        self.assertIn((1, 2), cells)
        self.assertNotIn((2, 2), cells)

    def test_danger_includes_active_explosion(self):
        board = [
            [INDESTRUCTIBLE] * 3,
            [INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 3,
        ]
        class FakeExp:
            cells = [(1, 1)]
            def is_active(self, t):
                return True
        game = _make_mock_game(board, explosions=[FakeExp()], current_time=0)
        self.assertIn((1, 1), _get_danger_cells(game))

    def test_cells_with_bombs(self):
        bombs = [_make_mock_bomb(1, 2), _make_mock_bomb(3, 4)]
        self.assertEqual(_cells_with_bombs(bombs), {(1, 2), (3, 4)})

    def test_ai_hunts_toward_visible_opponent(self):
        board = [
            [INDESTRUCTIBLE] * 5,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 5,
        ]
        ai = _make_mock_player(1, 2)
        ai.fire_power = 1
        opponent = _make_mock_player(3, 2)
        ai.is_ai = True
        game = _make_mock_game(board, players=[ai, opponent])
        direction, place_bomb = compute_ai_input(ai, game)
        self.assertFalse(place_bomb)
        self.assertGreater(direction[0], 0)

    def test_ai_bombs_soft_wall_blocking_opponent(self):
        board = [
            [INDESTRUCTIBLE] * 5,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, DESTRUCTIBLE, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 5,
        ]
        ai = _make_mock_player(1, 2)
        ai.fire_power = 2
        opponent = _make_mock_player(3, 2)
        ai.is_ai = True
        game = _make_mock_game(board, players=[ai, opponent])
        _, place_bomb = compute_ai_input(ai, game)
        self.assertTrue(place_bomb)

    def test_align_then_turn_centers_before_corner(self):
        ai = _make_mock_player(2, 1)
        ai._ai_last_dir = (1, 0)
        ai.pos[0] += 20
        self.assertFalse(_is_cell_centered(ai))
        self.assertEqual(_align_then_turn(ai, (0, 1)), (-1, 0))

        ai = _make_mock_player(2, 1)
        ai._ai_last_dir = (1, 0)
        ai.pos[0] -= 20
        self.assertEqual(_align_then_turn(ai, (0, 1)), (1, 0))

        ai = _make_mock_player(2, 1)
        ai._ai_last_dir = (1, 0)
        self.assertTrue(_is_cell_centered(ai))
        self.assertEqual(_align_then_turn(ai, (0, 1)), (0, 1))

    def test_ai_does_not_bomb_until_centered(self):
        board = [
            [INDESTRUCTIBLE] * 5,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 5,
        ]
        ai = _make_mock_player(1, 2)
        ai.fire_power = 2
        ai.pos[0] += 20
        opponent = _make_mock_player(3, 2)
        ai.is_ai = True
        game = _make_mock_game(board, players=[ai, opponent])
        _, place_bomb = compute_ai_input(ai, game)
        self.assertFalse(place_bomb)

    def test_centered_bot_bombs_a_brick_it_can_escape(self):
        board = [
            [INDESTRUCTIBLE] * 7,
            [INDESTRUCTIBLE, EMPTY, EMPTY, DESTRUCTIBLE, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 7,
        ]
        ai = _make_mock_player(2, 1)
        ai.fire_power = 1
        ai.is_ai = True
        ai.ai_personality = "normal"
        opponent = _make_mock_player(5, 5)
        game = _make_mock_game(board, players=[ai, opponent])
        _, place_bomb = compute_ai_input(ai, game)
        self.assertTrue(place_bomb)

    def test_adjacent_los_bombs_when_escape_exists(self):
        """Any safe LOS, including adjacent, is an attack."""
        board = [
            [INDESTRUCTIBLE] * 7,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 7,
        ]
        ai = _make_mock_player(2, 3)
        ai.fire_power = 2
        opponent = _make_mock_player(3, 3)
        ai.is_ai = True
        game = _make_mock_game(board, players=[ai, opponent])
        self.assertTrue(_opponent_in_blast_range_with_los(ai, game))
        _, place_bomb = compute_ai_input(ai, game)
        self.assertTrue(place_bomb)

    def test_bombs_blocking_crate_inside_blast_not_only_adjacent(self):
        board = [
            [INDESTRUCTIBLE] * 7,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, DESTRUCTIBLE, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 7,
        ]
        ai = _make_mock_player(1, 2)
        ai.fire_power = 2
        opponent = _make_mock_player(5, 2)
        ai.is_ai = True
        game = _make_mock_game(board, players=[ai, opponent])
        _, place_bomb = compute_ai_input(ai, game)
        self.assertTrue(place_bomb)

    def test_trapped_adjacent_opponent_is_bombed(self):
        board = [
            [INDESTRUCTIBLE] * 5,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 5,
        ]
        opponent = _make_mock_player(1, 1)
        ai = _make_mock_player(2, 1)
        ai.fire_power = 1
        ai.is_ai = True
        game = _make_mock_game(board, players=[ai, opponent])
        _, place_bomb = compute_ai_input(ai, game)
        self.assertTrue(place_bomb)

    def test_slow_escape_refuses_bomb(self):
        board = [
            [INDESTRUCTIBLE] * 5,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 5,
        ]
        ai = _make_mock_player(1, 2)
        ai.fire_power = 2
        ai.speed = 20
        opponent = _make_mock_player(3, 2)
        ai.is_ai = True
        game = _make_mock_game(board, players=[ai, opponent])
        self.assertFalse(_can_escape_after_bomb(ai, game, set()))
        _, place_bomb = compute_ai_input(ai, game)
        self.assertFalse(place_bomb)

    def test_flees_before_legacy_danger_lead(self):
        """A slow bot on a blast line leaves when the fuse race starts, not at 700 ms."""
        board = [
            [INDESTRUCTIBLE] * 5,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 5,
        ]
        ai = _make_mock_player(1, 1)
        ai.speed = 100
        bomb = _make_mock_bomb(2, 1, start_time=0, owner=ai)
        game = _make_mock_game(board, bombs=[bomb], players=[ai], current_time=BOMB_TIMER - 1000)
        danger = _get_danger_cells(game)
        self.assertNotIn((1, 1), danger)
        times = _danger_times(game)
        self.assertIn((1, 1), times)
        direction, _ = compute_ai_input(ai, game)
        self.assertTrue(direction[0] != 0 or direction[1] != 0)

    def test_think_interval_caches_intent(self):
        board = [
            [INDESTRUCTIBLE] * 5,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 5,
        ]
        ai = _make_mock_player(1, 2)
        opponent = _make_mock_player(3, 2)
        ai.is_ai = True
        game = _make_mock_game(board, players=[ai, opponent], current_time=0)
        compute_ai_input(ai, game)
        first_think = ai._ai_last_think_ms
        first_intent = ai._ai_intent_dir
        game.current_time = AI_THINK_INTERVAL_MS - 1
        compute_ai_input(ai, game)
        self.assertEqual(ai._ai_last_think_ms, first_think)
        self.assertEqual(ai._ai_intent_dir, first_intent)
        game.current_time = AI_THINK_INTERVAL_MS
        compute_ai_input(ai, game)
        self.assertEqual(ai._ai_last_think_ms, AI_THINK_INTERVAL_MS)

    def test_sticky_hunt_survives_opponent_teleport(self):
        board = [
            [INDESTRUCTIBLE] * 7,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 7,
        ]
        ai = _make_mock_player(1, 3)
        opponent = _make_mock_player(5, 3)
        ai.is_ai = True
        game = _make_mock_game(board, players=[ai, opponent], current_time=0)
        think_ai(ai, game)
        self.assertEqual(ai._ai_goal_kind, "hunt")
        goal = ai._ai_goal_cell
        self.assertIsNotNone(goal)
        opponent.pos = [1 * CELL_SIZE + CELL_SIZE // 2, 1 * CELL_SIZE + CELL_SIZE // 2]
        game.current_time = min(AI_STICKY_MS - 10, AI_THINK_INTERVAL_MS)
        step, _ = think_ai(ai, game)
        self.assertEqual(ai._ai_goal_cell, goal)
        self.assertEqual(ai._ai_goal_kind, "hunt")
        self.assertGreater(step[0], 0)

    def test_close_combat_prefers_hunt_over_nearby_powerup(self):
        board = [
            [INDESTRUCTIBLE] * 5,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 5,
        ]
        ai = _make_mock_player(1, 2)
        ai.fire_power = 1
        opponent = _make_mock_player(3, 2)
        pu = type("PU", (), {"x": 1, "y": 1, "type": "bomb"})()
        ai.is_ai = True
        game = _make_mock_game(board, players=[ai, opponent], powerups=[pu])
        direction, place_bomb = compute_ai_input(ai, game)
        self.assertFalse(place_bomb)
        self.assertGreater(direction[0], 0)

    def test_boss_collects_bonuses_and_spends_extra_bombs(self):
        from ai_controller import _powerup_limit, BOSS_POWERUP_HUNT_LIMIT, POWERUP_HUNT_LIMIT
        cpu = _make_mock_player(1, 1)
        cpu.ai_role = "cpu"
        cpu.ai_personality = "normal"
        boss = _make_mock_player(1, 1)
        boss.ai_role = "boss"
        boss.speed = 400
        self.assertGreaterEqual(_powerup_limit(boss), _powerup_limit(cpu))
        self.assertEqual(_powerup_limit(boss), BOSS_POWERUP_HUNT_LIMIT)
        self.assertGreater(BOSS_POWERUP_HUNT_LIMIT, POWERUP_HUNT_LIMIT)
        board = [
            [INDESTRUCTIBLE] * 5,
            [INDESTRUCTIBLE, EMPTY, EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 5,
        ]
        boss.pos = [2 * CELL_SIZE + CELL_SIZE // 2, 1 * CELL_SIZE + CELL_SIZE // 2]
        boss.fire_power = 1
        boss.bomb_capacity = 2
        boss.active_bombs = 1
        boss.is_ai = True
        game = _make_mock_game(board, players=[boss])
        _, place_bomb = compute_ai_input(boss, game)
        self.assertTrue(place_bomb)

    def test_personalities_change_bombing_and_goals(self):
        from ai_controller import _soft_walls_hit
        board = [
            [INDESTRUCTIBLE] * 9,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, DESTRUCTIBLE, EMPTY, EMPTY, DESTRUCTIBLE, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, DESTRUCTIBLE, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 9,
        ]
        ai = _make_mock_player(1, 1)
        ai.fire_power = 1
        ai.is_ai = True
        ai.ai_personality = "normal"
        far = _make_mock_player(7, 5)
        game = _make_mock_game(board, players=[ai, far])
        think_ai(ai, game)
        self.assertEqual(ai._ai_goal_kind, "farm")
        self.assertEqual(ai._ai_goal_cell, (5, 3))
        self.assertEqual(_soft_walls_hit(board, 5, 3, 1), 2)
        self.assertEqual(_soft_walls_hit(board, 1, 2, 1), 1)

        cautious = _make_mock_player(1, 1)
        cautious.fire_power = 1
        cautious.bomb_capacity = 3
        cautious.active_bombs = 1
        cautious.is_ai = True
        cautious.ai_personality = "cautious"
        _, second = think_ai(cautious, _make_mock_game(board, players=[cautious]))
        self.assertFalse(second)

        threatened = _make_mock_player(2, 3)
        threatened.fire_power = 3
        threatened.is_ai = True
        threatened.ai_personality = "cautious"
        hunter = _make_mock_player(4, 3)
        step, place = think_ai(threatened, _make_mock_game(board, players=[threatened, hunter]))
        self.assertFalse(place)
        self.assertEqual(threatened._ai_goal_kind, "retreat")
        self.assertIsNotNone(threatened._ai_goal_cell)
        self.assertGreater(
            abs(threatened._ai_goal_cell[0] - 4) + abs(threatened._ai_goal_cell[1] - 3),
            abs(2 - 4) + abs(3 - 3),
        )
        self.assertNotEqual(step, (1, 0))

        crazy = _make_mock_player(1, 3)
        crazy.fire_power = 1
        crazy.is_ai = True
        crazy.ai_personality = "crazy"
        opp = _make_mock_player(3, 3)
        qd = type("PU", (), {"x": 7, "y": 1, "type": "quad_damage"})()
        bomb_pu = type("PU", (), {"x": 1, "y": 5, "type": "bomb"})()
        think_ai(crazy, _make_mock_game(board, players=[crazy, opp], powerups=[qd, bomb_pu]))
        self.assertEqual(crazy._ai_goal_kind, "powerup")
        self.assertEqual(crazy._ai_goal_cell, (7, 1))

    def test_normal_does_not_bomb_a_far_line_of_sight(self):
        board = [
            [INDESTRUCTIBLE] * 9,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 9,
        ]
        ai = _make_mock_player(1, 1)
        ai.fire_power = 6
        ai.is_ai = True
        ai.ai_personality = "normal"
        opp = _make_mock_player(7, 1)
        game = _make_mock_game(board, players=[ai, opp])
        _, place = think_ai(ai, game)
        self.assertFalse(place)
        ai.ai_personality = "crazy"
        _, place = think_ai(ai, game)
        self.assertTrue(place)

    def test_quad_damage_preferred_over_closer_bomb_powerup(self):
        board = [
            [INDESTRUCTIBLE] * 7,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 7,
        ]
        ai = _make_mock_player(1, 1)
        opponent = _make_mock_player(5, 5)
        qd = type("PU", (), {"x": 4, "y": 1, "type": "quad_damage"})()
        bomb_pu = type("PU", (), {"x": 1, "y": 2, "type": "bomb"})()
        ai.is_ai = True
        game = _make_mock_game(board, players=[ai, opponent], powerups=[qd, bomb_pu])
        step, _ = think_ai(ai, game)
        self.assertEqual(ai._ai_goal_kind, "powerup")
        self.assertEqual(ai._ai_goal_cell, (4, 1))
        self.assertGreater(step[0], 0)

    def test_nearest_powerup_helper_prefers_qd(self):
        board = [
            [INDESTRUCTIBLE] * 5,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 5,
        ]
        qds = [type("PU", (), {"x": 3, "y": 1, "type": "quad_damage"})()]
        bombs = [type("PU", (), {"x": 1, "y": 2, "type": "bomb"})()]
        step = _nearest_powerup(board, 1, 1, bombs + qds, set(), set())
        self.assertEqual(step, (1, 0))

    def test_farm_bomb_on_a_cell_that_clears_a_brick(self):
        board = [
            [INDESTRUCTIBLE] * 7,
            [INDESTRUCTIBLE, EMPTY, EMPTY, DESTRUCTIBLE, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 7,
        ]
        ai = _make_mock_player(2, 1)
        ai.fire_power = 1
        ai.is_ai = True
        ai.ai_personality = "normal"
        opponent = _make_mock_player(5, 3)
        game = _make_mock_game(board, players=[ai, opponent])
        _, place_bomb = compute_ai_input(ai, game)
        self.assertTrue(place_bomb)

    def test_does_not_step_into_live_explosion(self):
        """A bot in a safe pocket must not walk into a cell that is already exploding."""
        board = [
            [INDESTRUCTIBLE] * 5,
            [INDESTRUCTIBLE, EMPTY, EMPTY, DESTRUCTIBLE, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE, DESTRUCTIBLE, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, DESTRUCTIBLE, DESTRUCTIBLE, DESTRUCTIBLE, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 5,
        ]
        ai = _make_mock_player(1, 2)
        ai.is_ai = True
        ai.speed = 287
        opponent = _make_mock_player(3, 1)
        explosion = type("Exp", (), {})()
        explosion.cells = [(1, 1), (2, 1)]
        explosion.start_time = 0
        explosion.is_active = lambda t: t < EXPLOSION_DURATION
        game = _make_mock_game(
            board, explosions=[explosion], players=[ai, opponent], current_time=80,
        )
        step, _ = think_ai(ai, game)
        self.assertNotEqual(step, (0, -1))
        direction, _ = compute_ai_input(ai, game)
        self.assertGreaterEqual(direction[1], 0)

    def test_spawn_l_does_not_jitter_on_first_corner(self):
        """After the opening bomb, wait in the safe L-arm instead of vibrating on the junction."""
        from bm_classes import Player
        from input_abstraction import Keys

        I, E, D = INDESTRUCTIBLE, EMPTY, DESTRUCTIBLE
        board = [
            [I] * 7,
            [I, E, E, D, D, D, I],
            [I, E, I, D, I, D, I],
            [I, D, D, D, D, D, I],
            [I, D, I, D, I, E, I],
            [I, D, D, D, E, E, I],
            [I] * 7,
        ]
        controls = {"up": Keys.W, "down": Keys.S, "left": Keys.A, "right": Keys.D, "bomb": Keys.SPACE}
        ai = Player(1, 1, (255, 0, 0), controls, "AI")
        ai.is_ai = True
        human = Player(5, 5, (0, 255, 0), None, "P")
        game = _make_mock_game(board, bombs=[], players=[ai, human])
        spawn_l = {(1, 1), (2, 1), (1, 2)}
        planted_at = None
        grid_changes_after_bomb = 0
        last_grid = ai.get_grid_pos()
        still_on_safe_cell = 0

        for t in range(0, BOMB_TIMER - 200, 16):
            game.current_time = t
            ai.update(16, board, game.bombs, t, game=game)
            grid = ai.get_grid_pos()
            if grid != last_grid:
                if planted_at is not None:
                    grid_changes_after_bomb += 1
                last_grid = grid
            if game.bombs and planted_at is None:
                planted_at = t
            if planted_at is not None and grid == (1, 2) and ai._ai_intent_dir == (0, 0):
                still_on_safe_cell += 16
            self.assertIn(grid, spawn_l)
            self.assertTrue(ai.alive)

        self.assertIsNotNone(planted_at)
        self.assertLess(grid_changes_after_bomb, 8)
        self.assertGreater(still_on_safe_cell, 400)
        self.assertEqual(ai._ai_goal_kind, "wait")

    def test_spawn_l_leaves_after_opening_blast(self):
        """Once the first crate is gone, the bot walks out of the spawn L."""
        from bm_classes import Player
        from input_abstraction import Keys

        I, E, D = INDESTRUCTIBLE, EMPTY, DESTRUCTIBLE
        board = [
            [I] * 7,
            [I, E, E, D, D, D, I],
            [I, E, I, D, I, D, I],
            [I, D, D, D, D, D, I],
            [I, D, I, D, I, E, I],
            [I, D, D, D, E, E, I],
            [I] * 7,
        ]
        controls = {"up": Keys.W, "down": Keys.S, "left": Keys.A, "right": Keys.D, "bomb": Keys.SPACE}
        ai = Player(1, 1, (255, 0, 0), controls, "AI")
        ai.is_ai = True
        human = Player(5, 5, (0, 255, 0), None, "P")
        game = _make_mock_game(board, bombs=[], players=[ai, human])
        visited_after_blast = set()
        for t in range(0, BOMB_TIMER + 2800, 16):
            game.current_time = t
            ai.update(16, board, game.bombs, t, game=game)
            expired = [bomb for bomb in list(game.bombs) if bomb.update(t)]
            for bomb in expired:
                bx, by = bomb.x, bomb.y
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = bx + dx, by + dy
                    if 0 <= ny < len(board) and 0 <= nx < len(board[0]) and board[ny][nx] == D:
                        board[ny][nx] = E
                        break
                if bomb.owner is not None:
                    bomb.owner.active_bombs = max(0, bomb.owner.active_bombs - 1)
                game.bombs.remove(bomb)
            if t >= BOMB_TIMER + 400:
                visited_after_blast.add(ai.get_grid_pos())
            if (3, 1) in visited_after_blast:
                break

        self.assertEqual(board[1][3], E)
        self.assertTrue(visited_after_blast & {(2, 1), (3, 1), (4, 1)})

    def test_leaves_own_bomb_while_the_fuse_is_still_long(self):
        """A fast bot used to wait on the lit cell until the exit was already late."""
        board = [
            [INDESTRUCTIBLE] * 9,
            *[[INDESTRUCTIBLE, *([EMPTY] * 7), INDESTRUCTIBLE] for _ in range(7)],
            [INDESTRUCTIBLE] * 9,
        ]
        ai = _make_mock_player(4, 4)
        ai.is_ai = True
        ai.speed = 287
        ai.ai_personality = "normal"
        opponent = _make_mock_player(7, 7)
        bomb = _make_mock_bomb(4, 4, start_time=0, fire_power=1, owner=ai)
        game = _make_mock_game(
            board, bombs=[bomb], players=[ai, opponent], current_time=BOMB_TIMER - 2500,
        )
        step, place = think_ai(ai, game)
        self.assertFalse(place)
        self.assertNotEqual(step, (0, 0))
        self.assertIn(ai._ai_goal_kind, ("wait", "flee"))

    def test_flee_steps_out_instead_of_centering_first(self):
        board = [
            [INDESTRUCTIBLE] * 5,
            [INDESTRUCTIBLE, INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, INDESTRUCTIBLE, EMPTY, INDESTRUCTIBLE, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 5,
        ]
        ai = _make_mock_player(2, 2)
        ai.pos[0] += 40
        ai.is_ai = True
        ai.speed = 287
        bomb = _make_mock_bomb(2, 2, start_time=0, fire_power=1, owner=ai)
        game = _make_mock_game(board, bombs=[bomb], players=[ai], current_time=BOMB_TIMER - 2000)
        step, _ = think_ai(ai, game)
        direction, _ = compute_ai_input(ai, game)
        self.assertEqual(step, (0, 1))
        self.assertEqual((int(direction[0]), int(direction[1])), (0, 1))

    def test_chained_bomb_is_lethal_at_the_earlier_fuse(self):
        board = [
            [INDESTRUCTIBLE] * 7,
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE, EMPTY, EMPTY, EMPTY, EMPTY, EMPTY, INDESTRUCTIBLE],
            [INDESTRUCTIBLE] * 7,
        ]
        ai = _make_mock_player(1, 1)
        ai.is_ai = True
        ai.speed = 287
        near = _make_mock_bomb(3, 2, start_time=200 - BOMB_TIMER, fire_power=1)
        chained = _make_mock_bomb(3, 1, start_time=0, fire_power=2)
        game = _make_mock_game(board, bombs=[chained, near], players=[ai], current_time=0)
        self.assertEqual(_danger_times(game)[(1, 1)], 200)
        step, _ = think_ai(ai, game)
        self.assertNotEqual(step, (0, 0))


if __name__ == "__main__":
    unittest.main()
