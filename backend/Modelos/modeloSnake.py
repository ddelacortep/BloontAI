"""
Snake DQN Agent — Backend con FastAPI + TensorFlow (Keras)

Entrena una IA para jugar al Snake usando Deep Q-Network (DQN).
Todo se almacena SOLO EN MEMORIA (RAM). Al reiniciar el servidor los datos desaparecen.

Endpoints disponibles:
  GET    /snake/status   — estado del agente: épocas, epsilon, mejor puntuación
  POST   /snake/train    — entrena el agente DQN durante N episodios
  POST   /snake/predict  — dado un estado (11 floats), devuelve la acción óptima
  POST   /snake/play     — la IA juega una partida completa y devuelve los frames
  DELETE /snake/reset    — elimina el agente y reinicia todo
"""

from __future__ import annotations

import random
import numpy as np
from collections import deque
from typing import Optional

import tensorflow as tf
from tensorflow.keras import layers, models

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ─── Configuración por defecto ────────────────────────────────────────────────
GRID_SIZE     = 20       # Tamaño del tablero (20×20 celdas)
STATE_SIZE    = 11       # 3 peligros + 4 dirección + 4 comida relativa
ACTION_SIZE   = 4        # arriba, derecha, abajo, izquierda
GAMMA         = 0.95     # Factor de descuento para recompensas futuras
EPSILON_START = 1.0      # Exploración inicial (100% aleatorio)
EPSILON_MIN   = 0.01     # Exploración mínima
EPSILON_DECAY = 0.995    # Decaimiento de epsilon por episodio
LEARNING_RATE = 0.001    # Tasa de aprendizaje del optimizador Adam
BATCH_SIZE    = 64       # Tamaño del mini-batch para replay
MEMORY_MAX    = 50_000   # Capacidad máxima del buffer de experiencia
TARGET_SYNC   = 10       # Sincronizar red target cada N episodios

# Direcciones: 0=arriba, 1=derecha, 2=abajo, 3=izquierda
DIRS = [(0, -1), (1, 0), (0, 1), (-1, 0)]

app = FastAPI(title="Snake DQN Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ══════════════════════════════════════════════════════════════════════════════
#  SNAKE GAME — Motor del juego (lógica pura, sin UI)
# ══════════════════════════════════════════════════════════════════════════════

class SnakeGame:
    """
    Motor del juego Snake.

    Estado expuesto al agente: 11 floats
      [0-2] peligro recto / derecha / izquierda  (1 = peligro, 0 = seguro)
      [3-6] dirección actual one-hot              (arriba, derecha, abajo, izquierda)
      [7-10] posición relativa de la comida       (arriba, derecha, abajo, izquierda)

    Acciones: 0 = arriba, 1 = derecha, 2 = abajo, 3 = izquierda.
    Recompensas: +10 comer, -10 morir, -0.01 paso normal, -5 timeout.
    """

    def __init__(self, grid_size: int = GRID_SIZE):
        self.grid_size = grid_size
        self.reset()

    def reset(self) -> list[float]:
        """Reinicia el juego y devuelve el estado inicial."""
        mid = self.grid_size // 2
        self.snake = [{"x": mid, "y": mid}]
        self.direction = 1                          # empieza mirando a la derecha
        self.food = self._random_food()
        self.score = 0
        self.steps = 0
        self.max_steps = self.grid_size ** 2 * 2    # límite para evitar bucles infinitos
        self.game_over = False
        return self.get_state()

    def step(self, action: int) -> dict:
        """
        Ejecuta una acción y devuelve { state, reward, done }.

        Reglas:
          - No se permite girar 180° (dirección opuesta).
          - Colisión con pared o con el propio cuerpo → game over (reward -10).
          - Comer comida → puntuación +1, reward +10, nueva comida.
          - Exceder max_steps → game over (reward -5) para evitar bucles.
        """
        if self.game_over:
            return {"state": self.get_state(), "reward": 0.0, "done": True}

        # No permitir giro de 180°
        opposite = (self.direction + 2) % 4
        if action != opposite:
            self.direction = action

        # Mover la cabeza
        head = dict(self.snake[0])
        dx, dy = DIRS[self.direction]
        head["x"] += dx
        head["y"] += dy
        self.steps += 1

        # Colisión con pared
        if not (0 <= head["x"] < self.grid_size and 0 <= head["y"] < self.grid_size):
            self.game_over = True
            return {"state": self.get_state(), "reward": -10.0, "done": True}

        # Colisión con cuerpo
        if any(s["x"] == head["x"] and s["y"] == head["y"] for s in self.snake):
            self.game_over = True
            return {"state": self.get_state(), "reward": -10.0, "done": True}

        self.snake.insert(0, head)
        reward = -0.01  # penalización mínima por paso (para incentivar eficiencia)

        # Comer comida
        if head["x"] == self.food["x"] and head["y"] == self.food["y"]:
            self.score += 1
            reward = 10.0
            self.food = self._random_food()
        else:
            self.snake.pop()  # no creció → quitar cola

        # Timeout
        if self.steps >= self.max_steps:
            self.game_over = True
            return {"state": self.get_state(), "reward": -5.0, "done": True}

        return {"state": self.get_state(), "reward": reward, "done": False}

    def get_state(self) -> list[float]:
        """
        Calcula el vector de estado de 11 dimensiones para el agente.

        Componentes:
          - Peligro en dirección recta, derecha e izquierda (3 floats)
          - Dirección actual codificada one-hot (4 floats)
          - Posición relativa de la comida respecto a la cabeza (4 floats)
        """
        head = self.snake[0]
        d = self.direction
        straight = DIRS[d]
        right = DIRS[(d + 1) % 4]
        left = DIRS[(d + 3) % 4]

        def danger(ddx: int, ddy: int) -> float:
            nx, ny = head["x"] + ddx, head["y"] + ddy
            if not (0 <= nx < self.grid_size and 0 <= ny < self.grid_size):
                return 1.0
            if any(s["x"] == nx and s["y"] == ny for s in self.snake):
                return 1.0
            return 0.0

        return [
            danger(straight[0], straight[1]),  # peligro recto
            danger(right[0], right[1]),         # peligro a la derecha
            danger(left[0], left[1]),           # peligro a la izquierda
            1.0 if d == 0 else 0.0,             # dirección arriba
            1.0 if d == 1 else 0.0,             # dirección derecha
            1.0 if d == 2 else 0.0,             # dirección abajo
            1.0 if d == 3 else 0.0,             # dirección izquierda
            1.0 if self.food["y"] < head["y"] else 0.0,  # comida arriba
            1.0 if self.food["x"] > head["x"] else 0.0,  # comida a la derecha
            1.0 if self.food["y"] > head["y"] else 0.0,  # comida abajo
            1.0 if self.food["x"] < head["x"] else 0.0,  # comida a la izquierda
        ]

    def _random_food(self) -> dict:
        """Genera comida en una celda no ocupada por la serpiente."""
        occupied = {(s["x"], s["y"]) for s in self.snake}
        while True:
            pos = {
                "x": random.randint(0, self.grid_size - 1),
                "y": random.randint(0, self.grid_size - 1),
            }
            if (pos["x"], pos["y"]) not in occupied:
                return pos


# ══════════════════════════════════════════════════════════════════════════════
#  DQN AGENT — Red neuronal con experience replay
# ══════════════════════════════════════════════════════════════════════════════

class DQNAgent:
    """
    Deep Q-Network Agent.

    Arquitectura de la red (idéntica para model y target_model):
      Dense(256, relu) → Dense(128, relu) → Dense(4, linear)
      Entrada: 11 floats (estado del juego)
      Salida:  4 Q-values (uno por acción posible)

    Estrategia: epsilon-greedy con decaimiento exponencial.
    Entrenamiento: experience replay con mini-batches aleatorios.
    Estabilidad: red target que se sincroniza periódicamente.
    """

    def __init__(
        self,
        state_size: int = STATE_SIZE,
        action_size: int = ACTION_SIZE,
    ):
        self.state_size = state_size
        self.action_size = action_size

        self.gamma = GAMMA
        self.epsilon = EPSILON_START
        self.epsilon_min = EPSILON_MIN
        self.epsilon_decay = EPSILON_DECAY
        self.learning_rate = LEARNING_RATE
        self.batch_size = BATCH_SIZE

        # Buffer de experiencia (deque con máximo fijo para eficiencia)
        self.memory: deque = deque(maxlen=MEMORY_MAX)

        # Red principal (se entrena cada paso) y red target (estabilidad)
        self.model = self._build_model()
        self.target_model = self._build_model()
        self.sync_target()

    def _build_model(self) -> tf.keras.Model:
        """
        Construye la red densa del DQN.

        Capa 1: Input(11) — define la forma de entrada.
        Capa 2: Dense(256, relu) — procesa el estado de 11 dimensiones.
        Capa 3: Dense(128, relu) — comprime la representación interna.
        Capa 4: Dense(4, linear) — produce los Q-values para cada acción.

        Se usa MSE como pérdida porque estamos regresando Q-values continuos.
        """
        model = models.Sequential([
            layers.Input(shape=(self.state_size,)),
            layers.Dense(256, activation="relu"),
            layers.Dense(128, activation="relu"),
            layers.Dense(self.action_size, activation="linear"),
        ])
        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=self.learning_rate),
            loss="mse",
        )
        return model

    def act(self, state: list[float]) -> int:
        """
        Elige una acción usando la estrategia epsilon-greedy.
          - Con probabilidad epsilon → acción aleatoria (exploración).
          - Con probabilidad (1 - epsilon) → acción con mayor Q-value (explotación).
        Usa model() directo en lugar de model.predict() para evitar overhead.
        """
        if random.random() < self.epsilon:
            return random.randint(0, self.action_size - 1)
        state_tensor = tf.constant([state], dtype=tf.float32)
        q_values = self.model(state_tensor, training=False).numpy()[0]
        return int(np.argmax(q_values))

    def act_greedy(self, state: list[float]) -> tuple[int, list[float]]:
        """Acción sin exploración (para jugar). Devuelve (acción, q_values)."""
        state_tensor = tf.constant([state], dtype=tf.float32)
        q_values = self.model(state_tensor, training=False).numpy()[0]
        return int(np.argmax(q_values)), q_values.tolist()

    def remember(
        self,
        state: list[float],
        action: int,
        reward: float,
        next_state: list[float],
        done: bool,
    ):
        """Almacena una transición (s, a, r, s', done) en el buffer de experiencia."""
        self.memory.append((state, action, reward, next_state, done))

    def train_step(self) -> float:
        """
        Realiza un paso de entrenamiento con un mini-batch aleatorio del buffer.
        Usa model() directo en lugar de predict() para mayor velocidad.

        Retorna la pérdida (loss) del paso de entrenamiento.
        """
        if len(self.memory) < self.batch_size:
            return 0.0

        batch = random.sample(self.memory, self.batch_size)
        states = np.array([t[0] for t in batch], dtype=np.float32)
        next_states = np.array([t[3] for t in batch], dtype=np.float32)

        # Predecir Q-values actuales y futuros en batch usando model() directo
        current_qs = self.model(tf.constant(states), training=False).numpy()
        future_qs = self.target_model(tf.constant(next_states), training=False).numpy()

        # Actualizar los Q-targets para las acciones tomadas
        for i, (_, action, reward, _, done) in enumerate(batch):
            if done:
                current_qs[i][action] = reward
            else:
                current_qs[i][action] = reward + self.gamma * np.max(future_qs[i])

        # Entrenar la red principal
        history = self.model.fit(states, current_qs, epochs=1, verbose=0)
        loss = history.history["loss"][0]

        # Decaer epsilon
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay

        return float(loss)

    def sync_target(self):
        """Copia los pesos de la red principal a la red target para estabilidad."""
        self.target_model.set_weights(self.model.get_weights())


# ══════════════════════════════════════════════════════════════════════════════
#  ESTADO GLOBAL
# ══════════════════════════════════════════════════════════════════════════════

class SnakeState:
    """Contenedor del estado mutable del servidor."""
    agent: Optional[DQNAgent] = None
    episodes_trained: int = 0
    best_score: int = 0
    scores_history: list[int] = []          # puntuación de cada episodio
    avg_scores_history: list[float] = []    # media móvil (últimos 100)
    loss_history: list[float] = []          # pérdida media por episodio

    def __init__(self):
        self.scores_history = []
        self.avg_scores_history = []
        self.loss_history = []

state = SnakeState()


# ══════════════════════════════════════════════════════════════════════════════
#  MODELOS PYDANTIC
# ══════════════════════════════════════════════════════════════════════════════

class TrainRequest(BaseModel):
    """Parámetros configurables para el entrenamiento."""
    episodes: int = 100       # Número de partidas de entrenamiento
    grid_size: int = GRID_SIZE

class PredictPayload(BaseModel):
    """Estado del juego para que el agente elija acción."""
    state: list[float]        # Vector de 11 floats

class PlayRequest(BaseModel):
    """Parámetros para que la IA juegue una partida."""
    grid_size: int = GRID_SIZE


# ══════════════════════════════════════════════════════════════════════════════
#  ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/snake/status")
def snake_status():
    """Devuelve el estado actual del agente: si existe, episodios entrenados, métricas."""
    return {
        "agent_ready": state.agent is not None,
        "episodes_trained": state.episodes_trained,
        "best_score": state.best_score,
        "epsilon": round(state.agent.epsilon, 4) if state.agent else EPSILON_START,
        "scores_history": state.scores_history[-200:],       # últimos 200
        "avg_scores_history": state.avg_scores_history[-200:],
        "loss_history": state.loss_history[-200:],
    }


@app.post("/snake/train")
def snake_train(req: TrainRequest):
    """
    Entrena el agente DQN durante N episodios.

    Proceso por episodio:
      1. Reiniciar el juego Snake.
      2. El agente observa el estado y elige una acción (epsilon-greedy).
      3. El juego ejecuta la acción y devuelve recompensa + nuevo estado.
      4. Se almacena la transición en el buffer de experiencia.
      5. Se ejecuta un paso de entrenamiento con experience replay.
      6. Al final del episodio: registrar métricas.
      7. Cada TARGET_SYNC episodios: sincronizar la red target.

    Retorna las métricas finales del entrenamiento.
    """
    # Crear agente si no existe
    if state.agent is None:
        state.agent = DQNAgent()

    agent = state.agent
    game = SnakeGame(grid_size=req.grid_size)

    episode_scores = []
    episode_losses = []

    for episode in range(req.episodes):
        current_state = game.reset()
        done = False

        # Jugar un episodio completo (solo recoger experiencia, rápido)
        while not done:
            action = agent.act(current_state)
            result = game.step(action)
            agent.remember(current_state, action, result["reward"], result["state"], result["done"])
            current_state = result["state"]
            done = result["done"]

        # Entrenar UNA VEZ al final del episodio (no cada paso)
        loss = agent.train_step()

        # Registrar métricas del episodio
        score = game.score
        episode_scores.append(score)
        episode_losses.append(round(loss, 6))

        state.scores_history.append(score)
        state.loss_history.append(round(loss, 6))

        # Media móvil de los últimos 100 episodios
        window = state.scores_history[-100:]
        avg = sum(window) / len(window)
        state.avg_scores_history.append(round(avg, 2))

        if score > state.best_score:
            state.best_score = score

        state.episodes_trained += 1

        # Sincronizar red target periódicamente
        if (episode + 1) % TARGET_SYNC == 0:
            agent.sync_target()

        # Log de progreso cada 10 episodios
        if (episode + 1) % 10 == 0:
            print(
                f"[Snake] Ep {state.episodes_trained} | "
                f"Score: {score} | Avg: {avg:.1f} | "
                f"Best: {state.best_score} | ε: {agent.epsilon:.3f}"
            )

    return {
        "message": f"Entrenamiento de {req.episodes} episodios completado.",
        "episodes_trained": state.episodes_trained,
        "best_score": state.best_score,
        "epsilon": round(agent.epsilon, 4),
        "last_scores": episode_scores[-20:],
        "avg_score": round(sum(episode_scores) / len(episode_scores), 2),
    }


@app.post("/snake/predict")
def snake_predict(payload: PredictPayload):
    """
    Dado un vector de estado de 11 floats, devuelve la acción óptima del agente.
    Usa la red principal (sin exploración) para la predicción.
    """
    if state.agent is None:
        raise HTTPException(400, "No hay agente entrenado. Llama /snake/train primero.")

    if len(payload.state) != STATE_SIZE:
        raise HTTPException(400, f"El estado debe tener {STATE_SIZE} valores, recibidos: {len(payload.state)}")

    action, q_values_list = state.agent.act_greedy(payload.state)
    action_names = ["arriba", "derecha", "abajo", "izquierda"]
    q_values = q_values_list

    return {
        "action": action,
        "action_name": action_names[action],
        "q_values": {name: round(float(q), 4) for name, q in zip(action_names, q_values_list)},
    }


@app.post("/snake/play")
def snake_play(req: PlayRequest):
    """
    La IA juega una partida completa y devuelve todos los frames para visualización.
    Cada frame contiene: snake, food, score, action, direction.
    Útil para renderizar la partida en el frontend sin lógica de juego en JS.
    """
    if state.agent is None:
        raise HTTPException(400, "No hay agente entrenado. Llama /snake/train primero.")

    game = SnakeGame(grid_size=req.grid_size)
    current_state = game.reset()
    frames = []

    done = False
    while not done:
        # Acción sin exploración (epsilon = 0 para jugar)
        action, _ = state.agent.act_greedy(current_state)

        frames.append({
            "snake": [dict(s) for s in game.snake],
            "food": dict(game.food),
            "score": game.score,
            "action": action,
            "direction": game.direction,
        })

        result = game.step(action)
        current_state = result["state"]
        done = result["done"]

    # Último frame (estado final)
    frames.append({
        "snake": [dict(s) for s in game.snake],
        "food": dict(game.food),
        "score": game.score,
        "action": -1,
        "direction": game.direction,
    })

    return {
        "frames": frames,
        "final_score": game.score,
        "total_steps": game.steps,
        "grid_size": req.grid_size,
    }


@app.delete("/snake/reset")
def snake_reset():
    """Elimina el agente entrenado y reinicia todas las métricas."""
    state.agent = None
    state.episodes_trained = 0
    state.best_score = 0
    state.scores_history = []
    state.avg_scores_history = []
    state.loss_history = []

    return {"message": "Agente Snake reiniciado."}


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("modeloSnake:app", host="0.0.0.0", port=8002, reload=False)
