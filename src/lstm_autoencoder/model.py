"""Compact LSTM sequence-to-sequence autoencoder (fixed configuration)."""

from __future__ import annotations

MODEL_SEED = 26073
LOOKBACK = 12
ENCODER_UNITS = 64
LATENT_DIM = 32
LEARNING_RATE = 0.001
EPOCHS = 30
BATCH_SIZE = 256
OPTIMIZER = "Adam"
LOSS = "mse"

ARCHITECTURE = (
    "Input(12, F) -> LSTM(64, return_sequences=False) -> Dense(32, relu) "
    "[latent 32] -> RepeatVector(12) -> LSTM(64, return_sequences=True) "
    "-> TimeDistributed(Dense(F)); loss=MSE, optimizer=Adam(lr=0.001)"
)


def set_global_seeds(seed: int = MODEL_SEED) -> None:
    """Fix Python/numpy/TensorFlow seeds for deterministic training."""
    import random

    import numpy as np

    random.seed(seed)
    np.random.seed(seed)
    import tensorflow as tf

    tf.keras.utils.set_random_seed(seed)


def build_model(n_features: int):
    """Construct the unfitted autoencoder (CPU-runnable, no GPU dependency)."""
    import tensorflow as tf

    from src.lstm_autoencoder.sequences import LOOKBACK as _LB

    assert _LB == LOOKBACK
    inputs = tf.keras.Input(shape=(LOOKBACK, n_features))
    encoded = tf.keras.layers.LSTM(ENCODER_UNITS, return_sequences=False)(inputs)
    latent = tf.keras.layers.Dense(LATENT_DIM, activation="relu")(encoded)
    repeated = tf.keras.layers.RepeatVector(LOOKBACK)(latent)
    decoded = tf.keras.layers.LSTM(ENCODER_UNITS, return_sequences=True)(repeated)
    outputs = tf.keras.layers.TimeDistributed(
        tf.keras.layers.Dense(n_features))(decoded)
    model = tf.keras.Model(inputs, outputs)
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=LEARNING_RATE),
                  loss=LOSS)
    return model
