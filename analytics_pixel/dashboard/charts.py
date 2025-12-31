from __future__ import annotations

from typing import List, Tuple

import pygame

from .theme import Theme


def draw_line_chart(
    surf: pygame.Surface,
    rect: pygame.Rect,
    *,
    points: List[Tuple[int, int]],
    color: Tuple[int, int, int] = Theme.ACCENT,
    grid: bool = True,
) -> None:
    """
    points: list of (x, y) already scaled to rect coordinates.
    """
    pygame.draw.rect(surf, Theme.PANEL, rect, border_radius=10)
    pygame.draw.rect(surf, Theme.BORDER, rect, width=1, border_radius=10)

    if grid:
        for i in range(1, 4):
            y = rect.y + (rect.h * i) // 4
            pygame.draw.line(surf, (35, 39, 48), (rect.x + 10, y), (rect.x + rect.w - 10, y), 1)

    if len(points) < 2:
        return

    pygame.draw.lines(surf, color, False, points, 2)

    # points markers
    for x, y in points:
        pygame.draw.circle(surf, color, (x, y), 3)
