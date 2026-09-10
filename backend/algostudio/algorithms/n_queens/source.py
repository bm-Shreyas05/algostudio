def n_queens(n):
    board = [-1] * n
    solutions = []
    place(board, 0, n, solutions)
    return solutions


def place(board, row, n, solutions):
    if row == n:
        solutions.append(list(board))
        return
    for col in range(n):
        if safe(board, row, col):
            board[row] = col
            place(board, row + 1, n, solutions)
            board[row] = -1


def safe(board, row, col):
    for previous in range(row):
        if board[previous] == col:
            return False
        if abs(board[previous] - col) == row - previous:
            return False
    return True
