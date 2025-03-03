

def circle_rect_collision(circle_center, circle_radius, rect):
    # all rectangle collision boxes in game are orthogonal, none are rotated
    
    def clamp(value, min_value, max_value):
        return max(min_value, min(value, max_value))
    
    closest_x = clamp(circle_center[0], rect.left, rect.right)
    closest_y = clamp(circle_center[1], rect.top, rect.bottom)
    dx = circle_center[0] - closest_x
    dy = circle_center[1] - closest_y
    return (dx*dx + dy*dy) < (circle_radius * circle_radius)

    