/**
 * Deep Q-Network Agent — TensorFlow.js
 * Red densa (11 → 256 → 128 → 4) con experience replay y epsilon-greedy.
 */
import * as tf from '@tensorflow/tfjs'

export default class DQNAgent {
  constructor(stateSize = 11, actionSize = 4) {
    this.stateSize = stateSize
    this.actionSize = actionSize

    this.gamma = 0.95
    this.epsilon = 1.0
    this.epsilonMin = 0.01
    this.epsilonDecay = 0.995
    this.learningRate = 0.001
    this.batchSize = 64
    this.memoryMaxLen = 50000

    this.memory = []
    this.model = this._buildModel()
    this.targetModel = this._buildModel()
    this._updateTarget()
  }

  _buildModel() {
    const model = tf.sequential()
    model.add(tf.layers.dense({ inputShape: [this.stateSize], units: 256, activation: 'relu' }))
    model.add(tf.layers.dense({ units: 128, activation: 'relu' }))
    model.add(tf.layers.dense({ units: this.actionSize, activation: 'linear' }))
    model.compile({ optimizer: tf.train.adam(this.learningRate), loss: 'meanSquaredError' })
    return model
  }

  _updateTarget() {
    this.targetModel.setWeights(this.model.getWeights())
  }

  act(state) {
    if (Math.random() < this.epsilon) {
      return Math.floor(Math.random() * this.actionSize)
    }
    return tf.tidy(() => {
      const input = tf.tensor2d([state])
      const prediction = this.model.predict(input)
      return prediction.argMax(1).dataSync()[0]
    })
  }

  remember(state, action, reward, nextState, done) {
    this.memory.push({ state, action, reward, nextState, done })
    if (this.memory.length > this.memoryMaxLen) this.memory.shift()
  }

  async train() {
    if (this.memory.length < this.batchSize) return 0

    const batch = []
    const indices = new Set()
    while (indices.size < this.batchSize) {
      indices.add(Math.floor(Math.random() * this.memory.length))
    }
    for (const i of indices) batch.push(this.memory[i])

    const states = batch.map(b => b.state)
    const nextStates = batch.map(b => b.nextState)

    const tensors = tf.tidy(() => {
      const stateTensor = tf.tensor2d(states)
      const nextStateTensor = tf.tensor2d(nextStates)
      const currentQs = this.model.predict(stateTensor)
      const futureQs = this.targetModel.predict(nextStateTensor)
      const currentData = currentQs.arraySync()
      const futureData = futureQs.arraySync()

      for (let i = 0; i < batch.length; i++) {
        const { action, reward, done } = batch[i]
        currentData[i][action] = done ? reward : reward + this.gamma * Math.max(...futureData[i])
      }

      return { stateTensor: tf.tensor2d(states), targetTensor: tf.tensor2d(currentData) }
    })

    const result = await this.model.fit(tensors.stateTensor, tensors.targetTensor, { epochs: 1, verbose: 0 })
    tensors.stateTensor.dispose()
    tensors.targetTensor.dispose()

    if (this.epsilon > this.epsilonMin) this.epsilon *= this.epsilonDecay
    return result.history.loss[0]
  }

  syncTarget() { this._updateTarget() }

  dispose() {
    this.model.dispose()
    this.targetModel.dispose()
  }
}
