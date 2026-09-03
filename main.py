import sys
import random as rd
import copy as cp

WATER = '.'
WALL = 'x'

MOVE = "MOVE"
NORTH = "N"
SOUTH = "S"
EAST = "E"
WEST = "W"

SURFACE = "SURFACE"

OFFSET = {
    NORTH: (0, -1),
    SOUTH: (0, 1),
    EAST: (1, 0),
    WEST: (-1, 0)
}

TORPEDO = "TORPEDO"
SONAR = "SONAR"
SILENCE = "SILENCE"
MINE = "MINE"
TRIGGER = "TRIGGER"

CD_TORPEDO = 3


class Tile:

    def __init__(self, t=WATER) -> None:
        self.type = t
        self.pos: tuple[int, int] = (0, 0)
        self.sector = -1

    def is_water(self):
        return self.type == WATER

    def is_wall(self):
        return self.type == WALL


class Grid:

    def __init__(self) -> None:
        self.lines: list[list[Tile]] = []

    def get(self, x, y=None):
        if y is None and type(x) == tuple:
            y = x[1]
            x = x[0]
        assert type(x) == int and type(y) == int
        return self.lines[y][x]

    def is_water(self, x, y=None):
        return self.is_valid(x, y) and self.get(x, y).is_water()

    def is_wall(self, x, y=None):
        return self.get(x, y).is_wall()

    def is_valid(self, x, y=None):
        if y is None and type(x) == tuple:
            y = x[1]
            x = x[0]
        assert type(x) == int and type(y) == int
        return 0 <= x < len(self.lines[-1]) and 0 <= y < len(self.lines)

    def get_sector_valid(self, sector):
        base_x = ((sector - 1) % 3) * 5
        base_y = ((sector - 1) // 3) * 5
        locations = []
        for i in range(5):
            for j in range(5):
                candidate = tadd((base_x, base_y), (i, j))
                if self.is_water(candidate):
                    locations.append(candidate)
        return locations


def debug(*args):
    print(*args, file=sys.stderr, flush=True)

def tadd(a, b) -> tuple:
    assert type(a) == tuple and type(b) == tuple and len(a) == len(b)
    return tuple(a[i] + b[i] for i in range(len(a)))

def tscale(a, x) -> tuple:
    assert type(a) == tuple and type(x) in [int, float]
    return tuple(v * x for v in a)

def tdist(a, b) -> int:
    assert type(a) == tuple and type(b) == tuple and len(a) == len(b)
    return sum([abs(a[i] - b[i]) for i in range(len(a))])

def teq(a, b) -> bool:
    assert type(a) == tuple and type(b) == tuple and len(a) == len(b)
    for i in range(len(a)):
        if a[i] != b[i]:
            return False
    return True

def t8co(a, b) -> bool:  # 8-connex
    assert type(a) == tuple and type(b) == tuple and len(a) == len(b) and len(a) == 2
    for i in range(-1, 2):
        for j in range(-1, 2):
            if b == tadd(a, (i, j)):
                return True
    return False

def get4co(a, exclude_center=False) -> list[tuple[int, int]]:
    assert type(a) == tuple and len(a) == 2
    connex = []
    for offset in list(OFFSET.values()) + [(0, 0)]:
            if exclude_center and offset == (0, 0):
                continue
            connex.append(tadd(a, offset))
    return connex

def get8co(a, exclude_center=False) -> list[tuple[int, int]]:
    assert type(a) == tuple and len(a) == 2
    connex = []
    for i in range(-1, 2):
        for j in range(-1, 2):
            if exclude_center and i == 0 and j == 0:
                continue
            connex.append(tadd(a, (i, j)))
    return connex


class Submarine:

    def __init__(self, player_id, name="") -> None:
        self.name = name
        self.pos: tuple[int, int] = (-1, -1)
        self.health = 0
        self.expected_health = 0
        self.id = player_id
        self.bans = []
        self.ban_map = dict()
        self.previous_banned = dict()

        self.cooldown = dict()
        self.cooldown[TORPEDO] = 0
        self.cooldown[SONAR] = 0
        self.cooldown[SILENCE] = 0
        self.cooldown[MINE] = 0  # not used in this league

        self.mines: list[tuple[int, int]] = []

        self.last_action: tuple[tuple[str]] = None  # type: ignore
        self.last = {power: (0, 0) for power in [TORPEDO, MINE, TRIGGER]}
        self.last_sonar: int = 1
        self.sonar_result: bool = False
        self.surface_pos = (0, 0)
        
        self.history: list[tuple] = []
        self.warnings = []
        self.possibles = []

    def ban(self, pos):
        self.bans.append(pos)
        self.ban_map[pos] = True

    def init_ban_map(self, values):
        for v in values:
            self.ban_map[v] = False

    def set_bans(self, ban_list):
        if type(ban_list) != list:
            ban_list = [ban_list]
        self.bans = ban_list
        self.reset_ban_map()
        for ban in self.bans:
            self.ban_map[ban] = True

    def reset_ban_map(self):
        for k in self.ban_map.keys():
            self.ban_map[k] = False

    def banned(self, pos):
        return self.ban_map[pos]

    def history_append(self, orders: str):
        full_action = []
        for order in orders.split('|'):
            full_action.append(tuple(order.split()))
        self.history.append(tuple(full_action))

    def get_last_torpedo(self):
        for action in self.history[-1]:
            if action[0] == TORPEDO:
                return (int(action[1]), int(action[2]))

    def get_last(self, power: str):
        for action in self.history[-1]:
            if action[0] == power:
                if len(action) == 3:
                    return (int(action[1]), int(action[2]))
                elif len(action) == 2:
                    return int(action[1])
                else:
                    return None

    def init_possible(self, grid):
        self.possibles = []
        for x in range(WIDTH):
            for y in range(HEIGHT):
                pos = (x, y)
                if grid.is_water(pos):
                    self.possibles.append(pos)

    def narrow(self, narrowed: list[tuple[int, int]]):
        if len(narrowed) == 0:
            return
        new_possibles = []
        for n in narrowed:
            if n in self.possibles:
                new_possibles.append(n)
        self.possibles = new_possibles

    def narrow_exclude(self, excluded: list[tuple[int, int]]):
        if len(excluded) == 0:
            return
        new_possibles = []
        for poss in self.possibles:
            if poss not in excluded:
                new_possibles.append(poss)
        self.possibles = new_possibles

    def did(self, power, step_back=-1):
        if len(self.history) == 0:
            return False
        action_tuple: tuple[str] = self.history[step_back]
        for action in action_tuple:
            if action[0] == power:
                return True
        return False

    def get_sonar_result(self, grid: Grid, enemy: "Submarine"):
        if self.name == "ALLY":
            return self.sonar_result
        return enemy.pos in grid.get_sector_valid(self.get_last(SONAR))

    def get_action(self, power, step_back=-1):
        if len(self.history) == 0:
            return None
        action_tuple: tuple[str] = self.history[step_back]
        for action in action_tuple:
            if action[0] == power:
                if power == SURFACE and self.name == "ALLY":
                    sector = (3 * (self.surface_pos[1] // 5) + (self.surface_pos[0] // 5)) + 1
                    return (action[0], str(sector))
                return action
        return None

    def movement_narrowing(self, grid: Grid, action: tuple[str]):

        if len(self.history) == 0:
            return

        jumps = [(0, 0)]  # contain all the possible next offsets
        w = action[0]
        
        if w == MOVE:
            offset = OFFSET[action[1]]  # type: ignore
            jumps = [tadd(jump, offset) for jump in jumps]

        elif w == SILENCE:
            all_offsets = []
            for offset in list(OFFSET.values()):
                for increment in range(4):
                    all_offsets.append(tscale(offset, increment + 1))
            all_offsets += [(0, 0)]
            jumps = [tadd(jump, offset) for offset in all_offsets for jump in jumps]

        new_possibles = []
        for pos in self.possibles:
            for jump in jumps:
                next_pos = tadd(pos, jump)
                if grid.is_water(next_pos):

                    all_good = True
                    if w == SILENCE and self.name == "ALLY":
                        dx = 1 if pos[0] < next_pos[0] else (-1 if pos[0] > next_pos[0] else 0)
                        dy = 1 if pos[1] < next_pos[1] else (-1 if pos[1] > next_pos[1] else 0)
                        offset = (dx, dy)
                        if not teq(offset, (0, 0)):
                            interpolation = tadd(pos, offset)
                            # debug(len(self.bans))
                            # debug(interpolation, self.previous_banned[interpolation])
                            while not teq(interpolation, next_pos):
                                if not grid.is_water(interpolation) or self.previous_banned[interpolation]:
                                    all_good = False
                                    break
                                interpolation = tadd(interpolation, offset)
                            if self.previous_banned[next_pos]:
                                all_good = False

                    if all_good:
                        new_possibles.append(next_pos)
        self.possibles = list(set(new_possibles))  # remove duplicates

    def print_possible(self, grid: Grid):

        for line in grid.lines:
            line_str = ""
            for tile in line:
                if tile.is_wall():
                    line_str += "#"
                else:
                    if tile.pos in self.possibles:
                        line_str += "o"
                    else:
                        line_str += "." if (tile.sector % 2) == 0 else ","
            debug(line_str)

    def compute_start_pos(self, grid: Grid):
        while True:
            x = rd.randint(0, WIDTH - 1)
            y = rd.randint(0, HEIGHT - 1)
            if grid.get(x, y).is_water() and grid.get(x, y).sector == 5:
                return (x, y)

    def do_movement(self, grid: Grid, opp, force_silence=False):
        directions = [NORTH, SOUTH, EAST, WEST]
        rd.shuffle(directions)

        all_cells = []
        for i  in range(15):
            for j in range(15):
                pos = (i, j)
                if grid.is_water(pos):
                    all_cells.append(pos)

        fitness = dict()
        for dir in directions:
            offset = OFFSET[dir]
            next_pos = tadd(self.pos, offset)
            if not self.banned(next_pos) and grid.is_water(next_pos):
                    
                visited = {pos: False for pos in cp.deepcopy(all_cells)}
                queue = []
                current = next_pos
                count = 0
                MAX_REG_SIZE = 20
                while count < MAX_REG_SIZE:
                    visited[current] = True
                    neighbors = [n for n in get4co(current, True) if not self.banned(n) and
                                                                grid.is_water(n) and
                                                                n not in queue and
                                                                not visited[n]]
                    
                    for n in neighbors:
                        queue.append(n)
                    count += len(neighbors)
                    if len(queue) == 0:
                        break
                    current = queue.pop(0)
                fitness[dir] = min(count, MAX_REG_SIZE)

        debug("Move fitness:", fitness)

        if len(fitness) > 0:
            if self.spotted() or force_silence:
                if self.ready(SILENCE):
                    return self.do_silence(grid, opp)
            
            best_fit = []
            for dir, v in fitness.items():
                if v == max(list(fitness.values())):
                    best_fit.append(dir)
            rd.shuffle(best_fit)
            
            return MOVE + " " + str(best_fit[0]) + " " + self.compute_charge(opp)
        
        return self.do_surface()
    
    def do_mine(self, grid: Grid, opp):

        if not self.ready(MINE):
            return None

        directions = [NORTH, SOUTH, EAST, WEST]
        best_dir = NORTH
        best_target = (0, 0)
        best_score = -1
        for candidate in directions:
            target = tadd(self.pos, OFFSET[candidate])
            score = -1
            if grid.is_water(target):
                score = sum([1 for n in get8co(target) if grid.is_water(n) and
                                                          n not in self.mines])
            if score > best_score and rd.random() > 0.5:
                best_dir = candidate
                best_score = score
                best_target = target

        if best_score == -1:
            return None

        self.mines.append(best_target)
        self.last[MINE] = best_target
        return MINE + " " + best_dir
    
    def do_trigger(self, grid: Grid, opp):

        if len(self.mines) == 0:
            return None
        
        rd.shuffle(self.mines)
        idx = 0
        to_pop = self.mines[idx]
        fitness = 0

        for i, mine in enumerate(self.mines):
            score = 0
            for possible in opp.possibles:
                if t8co(mine, possible):
                    score += 1
                    if teq(mine, possible):
                        score += 1

            # dont hit self
            if (abs(mine[0] - self.pos[0]) <= 1 and abs(mine[1] - self.pos[1]) <= 1):
                score = 0

            if score > fitness:
                to_pop = mine
                fitness = score
                idx = i

        if fitness >= min(5, len(opp.possibles)) and len(opp.possibles) < 20:
            self.last[TRIGGER] = self.mines.pop(idx)
            return TRIGGER + " " + str(to_pop[0]) + " " + str(to_pop[1])
        return None
    
    def do_silence(self, grid: Grid, opp):
        directions = [NORTH, SOUTH, EAST, WEST]
        rd.shuffle(directions)
        jumps = []
        for dir in directions:
            offset = OFFSET[dir]
            for idx in range(4):
                distance = idx + 1
                next_pos = tadd(self.pos, tscale(offset, distance))
                if not self.banned(next_pos) and \
                        grid.is_water(next_pos):
                    jumps.append((dir, distance))
                else:
                    break
        if len(jumps) == 0:
            return self.do_surface() #+ "|" + self.do_silence(grid, opp)
        
        rd.shuffle(jumps)
        # debug("SILENCE:", jumps)
        jump = jumps[0]
        for distance in range(1, jump[1] + 1):
            self.ban(tadd(self.pos, tscale(OFFSET[jump[0]], distance)))
        return SILENCE + " " + jump[0] + " " + str(jump[1])

    def do_torpedo(self, grid: Grid, opp):

        if self.ready(TORPEDO):
            targets = dict()
            for x in range(WIDTH):
                for y in range(HEIGHT):
                    candidate = (x, y)
                    if grid.is_water(candidate) and \
                            tdist(candidate, self.pos) <= 4 and \
                            (abs(candidate[0] - self.pos[0]) > 1 or \
                            abs(candidate[1] - self.pos[1]) > 1):
                        targets[candidate] = 0

            for target in targets:
                score = 0
                for possible in opp.possibles:
                    if t8co(target, possible):
                        score += 1
                        if teq(target, possible):
                            score += 1
                targets[target] = score

            final = rd.choice([target for target in targets if targets[target] == max(targets.values())])
            if targets[final] > 0 and targets[final] > len(opp.possibles) * 0.25:
                self.last[TORPEDO] = final
                self.cooldown[TORPEDO] = CD_TORPEDO
                return TORPEDO + " " + str(final[0]) + " " + str(final[1])

    def do_sonar(self, grid: Grid, opp):

        if not self.ready(SONAR):
            return

        max_val = 0
        max_key = 1

        for sector in range(1, 10):
            score = 0
            locations = grid.get_sector_valid(sector)
            for location in locations:
                if location in opp.possibles:
                    score += 1
            if score > max_val:
                max_val = score
                max_key = sector

        if max_val > len(opp.possibles) * 0.8:
            return None

        self.last_sonar = max_key  # type: ignore

        return SONAR + " " + str(self.last_sonar)

    def do_action(self, grid: Grid, opp):

        self.previous_banned = cp.deepcopy(self.ban_map)

        if not self.banned(self.pos):
            self.ban(self.pos)

        actions: list[str] = []

        emergency_surfaced = False

        if len(self.bans) > 30 and len(self.possibles) < 5 and self.ready(SILENCE):
            actions.append(self.do_surface())
            emergency_surfaced = True

        action_torpedo = self.do_torpedo(grid, opp)
        if action_torpedo is not None:
            actions.append(action_torpedo)

        action_mine = self.do_mine(grid, opp)
        if action_mine is not None:
            actions.append(action_mine)

        action_trigger = self.do_trigger(grid, opp)
        if action_trigger is not None:
            actions.append(action_trigger)

        action_sonar = self.do_sonar(grid, opp)
        if action_sonar is not None:
            actions.append(action_sonar)

        actions.append(self.do_movement(grid, opp, force_silence=emergency_surfaced))

        assert len(actions) > 0
        self.last_action = tuple(tuple(action.split()) for action in actions)  # type: ignore
        output = "|".join([action for action in actions if action is not None])

        return output

    def do_surface(self):
        self.flush_bans()
        self.set_bans(self.pos)
        self.surface_pos = self.pos
        return SURFACE

    def flush_bans(self):
        self.bans = []
        self.reset_ban_map()

    def ready(self, power: str) -> bool:
        assert power in [TORPEDO, SONAR, SILENCE, MINE]
        return self.cooldown[power] == 0

    def spotted(self):
        return len(self.possibles) < 20

    def compute_charge(self, enemy: "Submarine") -> str:
        proba_rd = 0.25
        powers = [SILENCE, MINE, TORPEDO, SONAR]
        if len(enemy.possibles) > 80:
            proba_rd = 0.1
        if len(enemy.possibles) <= 10:
            powers = [TORPEDO, SILENCE]
        if self.spotted():
            powers = [SILENCE] + powers
        if rd.random() < proba_rd:
            rd.shuffle(powers)
        for power in powers:
            if self.cooldown[power] > 0:
                return power
        return ""

    def health_expected(self) -> bool:
        return self.health == self.expected_health

    def action_narrowing(self, grid: Grid, enemy: "Submarine"):

        ### SELF ACTIONS ###
        self_objects = [(self, TORPEDO), (self, TRIGGER)]
        enemy_objects = [(enemy, TORPEDO), (enemy, TRIGGER)]
        self_powers_used = 0
        enemy_powers_used = 0
        for obj in self_objects:
            submarine, power = obj
            if submarine.did(power):
                self_powers_used += 1
        for obj in enemy_objects:
            submarine, power = obj
            if submarine.did(power):
                enemy_powers_used += 1

        # narrow sonar
        if enemy.did(SONAR):
            cells = grid.get_sector_valid(enemy.last_sonar)
            if enemy.get_sonar_result(grid, self):
                self.narrow(cells)
            else:
                self.narrow_exclude(cells)
    
        # narrow if enemy torpedo/trigger misses
        if self.health_expected():
            candidates = []
            for power in [TORPEDO, TRIGGER]:
                if enemy.did(power):
                    candidates += get8co(enemy.get_last(power))
            candidates = list(set(candidates))
            self.narrow_exclude(candidates)

        # narrow if enemy hit (assume self wont hit itself)
        else:
            delta = self.expected_health - self.health
            candidates: list[tuple[int, int]] = []
            if enemy_powers_used == 1:
                for power in [TORPEDO, TRIGGER]:
                    if enemy.did(power):
                        last_power_pos = enemy.get_last(power)
                        assert type(last_power_pos) == tuple[int, int]
                        if delta == 2:
                            candidates = [last_power_pos]
                            break
                        elif delta == 1:
                            candidates = get8co(last_power_pos, exclude_center=True)

            elif enemy_powers_used == 2:
                candidates = []
                for power in [TORPEDO, TRIGGER]:
                    if enemy.did(power):
                        last_power_pos = enemy.get_last(power)
                        assert type(last_power_pos) == tuple[int, int]
                        if delta == 4:
                            candidates += [last_power_pos]
                        elif delta == 1:
                            candidates += get8co(last_power_pos, exclude_center=True)
                        else:
                            candidates += get8co(last_power_pos)
            self.narrow(candidates)

        if len(self.history) > 0:
            last_actions = self.history[-1]
            for action in last_actions:
                old_possible_count = len(self.possibles)
                power = action[0]
                if power in [MOVE, SILENCE]:
                    self.movement_narrowing(grid, action)
    
                elif power == SURFACE:
                    # narrow if surface
                    sector = int(self.get_action(SURFACE)[1])  # type: ignore
                    self.narrow(grid.get_sector_valid(sector))
    
                elif power == TORPEDO:
                    # narrow around torpedo
                    _, x, y = self.get_action(TORPEDO)  # type: ignore
                    base = (int(x), int(y))
                    candidates = []
                    torpedo_range = 4
                    for i in range(-torpedo_range, torpedo_range + 1):
                        for j in range(-torpedo_range, torpedo_range + 1):
                            candidate = tadd(base, (i, j))
                            if grid.is_water(candidate) and \
                                    tdist(candidate, base) <= torpedo_range:
                                candidates.append(candidate)
                    self.narrow(candidates)

                if self.name == "ALLY" and False:
                    debug(power, ":", old_possible_count, "->", len(self.possibles))
                    
        if self.name == "ALLY" and self.pos not in self.possibles:
            self.warnings.append("CORRUPTED self.possibles")


################################################
#################     MAIN     #################
################################################

rd.seed(42)

WIDTH, HEIGHT, my_id = [int(i) for i in input().split()]

grid = Grid()
sub = Submarine(my_id, "ALLY")
opp = Submarine(1 - my_id, "ENEMY")

for iy in range(HEIGHT):
    line = input()
    grid.lines.append([])
    for ix, c in enumerate(line):
        new_tile = Tile(c)
        new_tile.pos = (ix, iy)
        new_tile.sector = 3 * (iy // 5) + (ix // 5) + 1
        grid.lines[-1].append(new_tile)

# determine starting position
start_pos: tuple[int, int] = sub.compute_start_pos(grid)
sub.pos = start_pos
print(start_pos[0], start_pos[1])

# game loop
sub.init_possible(grid)
sub.init_ban_map([(x, y) for x in range(-1, 16) for y in range(-1, 16)])
opp.init_possible(grid)

step_index = 0
last_sub_order = "NA"

while True:
    step_index += 1
    x, y, my_life, opp_life, torpedo_cooldown, sonar_cooldown, silence_cooldown, mine_cooldown = [int(i) for i in input().split()]

    sub.pos = (x, y)
    sub.health = my_life
    sub.cooldown[TORPEDO] = torpedo_cooldown
    sub.cooldown[SONAR] = sonar_cooldown
    sub.cooldown[SILENCE] = silence_cooldown
    sub.cooldown[MINE] = mine_cooldown

    if len(opp.possibles) == 0:  # hard reset if miscalculation
        opp.init_possible(grid)
        opp.warnings.append("EMPTY POSSIBLES")

    if len(sub.warnings) > 0:
        debug("ALLY WARNING:", sub.warnings)
    if len(opp.warnings) > 0:
        debug("ENEMY WARNING:", opp.warnings)

    opp.health = opp_life

    sonar_result = input() == 'Y'
    opp_orders = input()

    sub.history_append(last_sub_order)
    sub.sonar_result = sonar_result
    opp.history_append(opp_orders)

    if sub.did(SURFACE): sub.expected_health -= 1
    if opp.did(SURFACE): opp.expected_health -= 1

    sub.action_narrowing(grid, opp)
    opp.action_narrowing(grid, sub)

    sub.expected_health = sub.health
    opp.expected_health = opp.health

    debug(sub.name + " possible:", len(sub.possibles), "\t", sub.possibles)
    debug(opp.name + " possible:", len(opp.possibles), "\t", opp.possibles)
    # sub.print_possible(grid)
    # opp.print_possible(grid)

    last_sub_order = sub.do_action(grid, opp)
    print(last_sub_order)