def hanoi(disks):
    moves = []
    pegs = {}
    pegs["A"] = []
    pegs["B"] = []
    pegs["C"] = []
    for size in range(disks, 0, -1):
        pegs["A"].append(size)
    move(disks, "A", "C", "B", pegs, moves)
    return moves


def move(count, source, target, spare, pegs, moves):
    if count == 0:
        return
    move(count - 1, source, spare, target, pegs, moves)
    disk = pegs[source].pop()
    pegs[target].append(disk)
    moves.append([disk, source, target])
    move(count - 1, spare, target, source, pegs, moves)
