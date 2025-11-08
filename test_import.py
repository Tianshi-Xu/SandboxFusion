from mpl_toolkits.mplot3d import Axes3D
import datetime
from sympy import symbols, Eq, solve

import json
import requests  # pip install requests

payload = {
    "code": """import numpy as np\nfrom scipy.optimize import fsolve\n\n# Let's solve the system properly\n# We have x + y + z = 75\n# And the inequalities x - yz < y - zx and y - zx < z - xy\n\n# Substituting z = 75 - x - y\n# First inequality: x - y(75-x-y) < y - (75-x-y)x\n# Simplifies to: x < y\n\n# Second inequality: y - (75-x-y)x < (75-x-y) - xy\n# Simplifies to: 2y - 74x + 3xy < 75\n\n# So we have:\n# x < y\n# y < (75 + 74x)/(2 + 3x) when x > -2/3\n\n# Let's find the boundary lines\n# Line 1: x = y\n# Line 2: y = (75 + 74x)/(2 + 3x)\n\n# Find intersection of these lines\n# x = (75 + 74x)/(2 + 3x)\n# x(2 + 3x) = 75 + 74x\n# 2x + 3x^2 = 75 + 74x\n# 3x^2 - 72x - 75 = 0\n# x^2 - 24x - 25 = 0\n\n# Solve x^2 - 24x - 25 = 0\na, b, c = 1, -24, -25\ndiscriminant = b**2 - 4*a*c\nx1 = (-b + np.sqrt(discriminant))/(2*a)\nx2 = (-b - np.sqrt(discriminant))/(2*a)\n\nprint(f'Roots: x1 = {x1}, x2 = {x2}')\n\n# Check if they're valid\nfor i, root in enumerate([x1, x2]):\n    y = root\n    z = 75 - root - root\n    print(f'Point {i+1}: ({root}, {root}, {z})')\n    \n# Let's also check the boundaries\n# When x approaches -2/3, y approaches infinity\n# When x approaches infinity, y approaches x\n\n# Let's check some boundary points\nboundary_points = []\n\n# Point where x = -2/3 (limit case)\n# But we need x > -2/3 for valid solution\n\n# Let's find where y = (75 + 74x)/(2 + 3x) intersects x = 0\n# When x = 0: y = 75/2 = 37.5\n# Point: (0, 37.5, 37.5)\n\n# When y = x: x = (75 + 74x)/(2 + 3x)\n# As calculated: x = 25 or x = -1\n\n# Check point (0, 37.5, 37.5)\nprint('\\nChecking boundary point (0, 37.5, 37.5):')\nx, y, z = 0, 37.5, 37.5\nlhs1 = x - y*z\nrhs1 = y - z*x\nlhs2 = y - z*x\nrhs2 = z - x*y\nprint(f'Inequality 1: {lhs1} < {rhs1} = {lhs1 < rhs1}')\nprint(f'Inequality 2: {lhs2} < {rhs2} = {lhs2 < rhs2}')\n\n# Check point (25, 25, 25) - this should be on boundary\nprint('\\nChecking point (25, 25, 25):')\nx, y, z = 25, 25, 25\nlhs1 = x - y*z\nrhs1 = y - z*x\nlhs2 = y - z*x\nrhs2 = z - x*y\nprint(f'Inequality 1: {lhs1} < {rhs1} = {lhs1 < rhs1}')\nprint(f'Inequality 2: {lhs2} < {rhs2} = {lhs2 < rhs2}')\n\n# Check point (-1, -1, 77)\nprint('\\nChecking point (-1, -1, 77):')\nx, y, z = -1, -1, 77\nlhs1 = x - y*z\nrhs1 = y - z*x\nlhs2 = y - z*x\nrhs2 = z - x*y\nprint(f'Inequality 1: {lhs1} < {rhs1} = {lhs1 < rhs1}')\nprint(f'Inequality 2: {lhs2} < {rhs2} = {lhs2 < rhs2}')
""",
    "language": "python",
}

response = requests.post(
    "http://localhost:8081/run_code",
    headers={"Content-Type": "application/json"},
    data=json.dumps(payload),
    timeout=60,
)

print("Status:", response.status_code)
print("Output:\n", response.text)
