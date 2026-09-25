"""AI vs AI matches: targeting, hunting, and full simulated rounds."""
import os
import random
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import open_board, silence_sounds

from ai_controller import _alive_opponents, think_ai
from bm_classes import Game, Player

silence_sounds()


def _ai_player(x, y, name):
    player = Player(x, y, (200, 40, 40), None, name)
    player.is_ai = True
    player.ai_role = "cpu"
    player.is_local = False
    return player


def _start_cpu_match(seed, ai_count=2):
    random.seed(seed)
    game = Game()
    game.prep_num_players = 0
    game.prep_ai_count = ai_count
    game._cached_status = None
    game.init_game()
    game.game_state = "playing"
    game.game_start_time = 10 ** 12
    game.round_start_time = 0
    game.crushing_walls_active = False
    game.dt = 16
    return game


def _simulate(game, duration_ms, dt=16):
    with patch("bm_classes.get_pressed_keys", return_value={}), patch(
        "bm_classes.is_key_pressed", return_value=False
    ):
        for t in range(0, duration_ms, dt):
            game.simulate(dt, now_ms=t)


def _spawn_pocket(player):
    x, y = player.start_grid_x, player.start_grid_y
    cells = {(x, y)}
    cells.add((x + 1, y) if x <= 2 else (x - 1, y))
    cells.add((x, y + 1) if y <= 2 else (x, y - 1))
    return cells


class TestAIvsAI(unittest.TestCase):
    def test_alive_opponents_are_other_cpus_when_no_human(self):
        a = _ai_player(1, 1, "A")
        b = _ai_player(3, 1, "B")
        game = type("G", (), {"players": [a, b]})()
        self.assertEqual(_alive_opponents(a, game), [b])
        self.assertEqual(_alive_opponents(b, game), [a])

    def test_alive_opponents_prefer_living_human(self):
        cpu_a = _ai_player(1, 1, "A")
        cpu_b = _ai_player(3, 1, "B")
        human = _ai_player(5, 1, "H")
        human.is_ai = False
        game = type("G", (), {"players": [cpu_a, cpu_b, human]})()
        self.assertEqual(_alive_opponents(cpu_a, game), [human])
        human.alive = False
        self.assertEqual(_alive_opponents(cpu_a, game), [cpu_b])

    def test_two_cpus_hunt_each_other_on_open_corridor(self):
        board = open_board(9, 5)
        a = _ai_player(1, 2, "A")
        b = _ai_player(7, 2, "B")
        game = Game()
        game.board = board
        game.grid_width = 9
        game.grid_height = 5
        game.players = [a, b]
        game.bombs = []
        game.explosions = []
        game.powerups = []
        game.game_state = "playing"
        game.game_start_time = 10 ** 12
        game.round_start_time = 0
        game.current_time = 0
        game.dt = 16
        start_dist = abs(a.get_grid_pos()[0] - b.get_grid_pos()[0])
        step_a, _ = think_ai(a, game)
        step_b, _ = think_ai(b, game)
        self.assertGreater(step_a[0], 0)
        self.assertLess(step_b[0], 0)
        _simulate(game, 2500)
        end_dist = abs(a.get_grid_pos()[0] - b.get_grid_pos()[0])
        fought = bool(game.bombs) or bool(game.explosions) or (not a.alive) or (not b.alive)
        self.assertTrue(fought or end_dist < start_dist)
        self.assertGreater(a.cells_walked + b.cells_walked, 0)

    def test_two_cpus_play_a_maze_round(self):
        """Full sim: both CPUs target each other, plant, and break crates."""
        game = _start_cpu_match(0, ai_count=2)
        ais = [p for p in game.players if p.is_ai]
        humans = [p for p in game.players if not p.is_ai]
        self.assertEqual(len(ais), 2)
        self.assertEqual(humans, [])
        self.assertEqual(_alive_opponents(ais[0], game), [ais[1]])
        self.assertEqual(_alive_opponents(ais[1], game), [ais[0]])
        crates_before = game.count_destroyable_cells()
        _simulate(game, 8000)
        self.assertGreater(sum(p.cells_walked for p in ais), 4)
        self.assertGreater(sum(p.walls_destroyed for p in ais), 0)
        self.assertLess(game.count_destroyable_cells(), crates_before)
        alive = [p for p in ais if p.alive]
        if len(alive) == 2:
            self.assertEqual(_alive_opponents(alive[0], game), [alive[1]])

    def test_maze_cpus_survive_own_opening_blast(self):
        """Regression: waiting out a fuse must not walk into the still-live blast."""
        for seed in range(6):
            game = _start_cpu_match(seed, ai_count=2)
            ais = [p for p in game.players if p.is_ai]
            pockets = {id(p): _spawn_pocket(p) for p in ais}
            _simulate(game, 4000)
            suicides = [
                p for p in ais
                if (not p.alive) and p.players_killed == 0 and p.get_grid_pos() in pockets[id(p)]
            ]
            self.assertEqual(
                suicides,
                [],
                "seed %s died in spawn from their own opening bomb: %s"
                % (seed, [(p.name, p.get_grid_pos()) for p in suicides]),
            )

    def test_three_cpus_all_act_in_ffa(self):
        game = _start_cpu_match(1, ai_count=3)
        ais = [p for p in game.players if p.is_ai]
        self.assertEqual(len(ais), 3)
        for bot in ais:
            others = _alive_opponents(bot, game)
            self.assertEqual(len(others), 2)
            self.assertNotIn(bot, others)
        _simulate(game, 6000)
        movers = [p for p in ais if p.cells_walked >= 1 or p.walls_destroyed >= 1]
        self.assertGreaterEqual(len(movers), 2)
        self.assertGreater(sum(p.walls_destroyed for p in ais), 0)


if __name__ == "__main__":
    unittest.main()
