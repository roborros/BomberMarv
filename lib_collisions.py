

def circle_rect_collision(circle_center, circle_radius, rect):
    # all rectangle collision boxes in game are orthogonal, none are rotated
    # rect is a sequence [x, y, width, height]
    cx, cy = circle_center[0], circle_center[1]
    rect_left = rect[0]
    rect_right = rect_left + rect[2]
    rect_top = rect[1]
    rect_bottom = rect_top + rect[3]

    closest_x = rect_left if cx < rect_left else (rect_right if cx > rect_right else cx)
    closest_y = rect_top if cy < rect_top else (rect_bottom if cy > rect_bottom else cy)
    dx = cx - closest_x
    dy = cy - closest_y
    return (dx * dx + dy * dy) < (circle_radius * circle_radius)

    