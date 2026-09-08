from collections import deque
import heapq

q = deque([1, 2, 3])
q.append(4)
q.appendleft(0)
front = q.popleft()
back = q.pop()
print(list(q), front, back)

h = []
for v in [5, 1, 4, 2]:
    heapq.heappush(h, v)
smallest = heapq.heappop(h)
print(smallest, sorted(h))
