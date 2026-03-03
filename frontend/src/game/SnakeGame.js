/**
 * Snake Game Engine — lógica pura sin dependencias de UI.
 * Estado expuesto al agente: 11 floats (peligro + dirección + comida relativa).
 * Acciones: 0 = arriba, 1 = derecha, 2 = abajo, 3 = izquierda
 */

const DIRS = [
  [0, -1], // 0 arriba
  [1, 0],  // 1 derecha
  [0, 1],  // 2 abajo
  [-1, 0], // 3 izquierda
]

export default class SnakeGame {
  constructor(gridSize = 20) {
    this.gridSize = gridSize
    this.reset()
  }

  reset() {
    const mid = Math.floor(this.gridSize / 2)
    this.snake = [{ x: mid, y: mid }]
    this.direction = 1
    this.food = this._randomFood()
    this.score = 0
    this.steps = 0
    this.maxSteps = this.gridSize * this.gridSize * 2
    this.gameOver = false
    return this.getState()
  }

  step(action) {
    if (this.gameOver) return { state: this.getState(), reward: 0, done: true }

    const opposite = (this.direction + 2) % 4
    if (action !== opposite) this.direction = action

    const head = { ...this.snake[0] }
    const [dx, dy] = DIRS[this.direction]
    head.x += dx
    head.y += dy
    this.steps++

    if (head.x < 0 || head.x >= this.gridSize || head.y < 0 || head.y >= this.gridSize) {
      this.gameOver = true
      return { state: this.getState(), reward: -10, done: true }
    }

    if (this.snake.some(s => s.x === head.x && s.y === head.y)) {
      this.gameOver = true
      return { state: this.getState(), reward: -10, done: true }
    }

    this.snake.unshift(head)
    let reward = -0.01

    if (head.x === this.food.x && head.y === this.food.y) {
      this.score++
      reward = 10
      this.food = this._randomFood()
    } else {
      this.snake.pop()
    }

    if (this.steps >= this.maxSteps) {
      this.gameOver = true
      return { state: this.getState(), reward: -5, done: true }
    }

    return { state: this.getState(), reward, done: false }
  }

  getState() {
    const head = this.snake[0]
    const dir = this.direction
    const straight = DIRS[dir]
    const right = DIRS[(dir + 1) % 4]
    const left = DIRS[(dir + 3) % 4]

    const danger = (dx, dy) => {
      const nx = head.x + dx
      const ny = head.y + dy
      if (nx < 0 || nx >= this.gridSize || ny < 0 || ny >= this.gridSize) return 1
      if (this.snake.some(s => s.x === nx && s.y === ny)) return 1
      return 0
    }

    return [
      danger(straight[0], straight[1]),
      danger(right[0], right[1]),
      danger(left[0], left[1]),
      dir === 0 ? 1 : 0,
      dir === 1 ? 1 : 0,
      dir === 2 ? 1 : 0,
      dir === 3 ? 1 : 0,
      this.food.y < head.y ? 1 : 0,
      this.food.x > head.x ? 1 : 0,
      this.food.y > head.y ? 1 : 0,
      this.food.x < head.x ? 1 : 0,
    ]
  }

  _randomFood() {
    const occupied = new Set(this.snake.map(s => `${s.x},${s.y}`))
    let pos
    do {
      pos = {
        x: Math.floor(Math.random() * this.gridSize),
        y: Math.floor(Math.random() * this.gridSize),
      }
    } while (occupied.has(`${pos.x},${pos.y}`))
    return pos
  }
}
