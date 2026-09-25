

def circle_rect_collision(circle_center, circle_radius, rect):
    # all rectangle collision boxes in game are orthogonal, none are rotated
    # rect is a sequence [x, y, width, height]
    
    def clamp(value, min_value, max_value):
        return max(min_value, min(value, max_value))
    
    rect_left = rect[0]
    rect_right = rect[0] + rect[2]
    rect_top = rect[1]
    rect_bottom = rect[1] + rect[3]
    
    closest_x = clamp(circle_center[0], rect_left, rect_right)
    closest_y = clamp(circle_center[1], rect_top, rect_bottom)
    dx = circle_center[0] - closest_x
    dy = circle_center[1] - closest_y
    return (dx*dx + dy*dy) < (circle_radius * circle_radius)

    