from bm_params import *
import random


def clear_safe_zone(board, sx, sy, offsets):
    for dx, dy in offsets:
        nx, ny = sx + dx, sy + dy
        if 0 <= nx < GRID_WIDTH and 0 <= ny < GRID_HEIGHT:
            if board[ny][nx] == DESTRUCTIBLE:
                board[ny][nx] = EMPTY

def get_random_L_pattern():
    patterns = [
        [(0,0), (1,0), (0,1)],
        
        [(0,0), (-1,0), (0,1)],
        [(0,0), (1,0), (0,-1)],
        [(0,0), (-1,0), (0,-1)],
        [(0,0), (0,1), (1,1)],
        [(0,0), (0,1), (-1,1)],
        [(0,0), (0,-1), (1,-1)],
        [(0,0), (0,-1), (-1,-1)]
    ]
    return random.choice(patterns)

def generate_maze():
    board = [[EMPTY for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
    for y in range(GRID_HEIGHT):
        for x in range(GRID_WIDTH):
            if x == 0 or y == 0 or x == GRID_WIDTH - 1 or y == GRID_HEIGHT - 1:
                board[y][x] = INDESTRUCTIBLE
            elif x % 2 == 0 and y % 2 == 0:
                board[y][x] = INDESTRUCTIBLE
            elif random.random() < 0.7:
                board[y][x] = DESTRUCTIBLE
    return board