from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import ttk

CONFIG_PATH = Path(__file__).resolve().parents[2] / "aether_settings.json"
DEFAULTS = {
    "scroll_threshold": 0.012,
    "scroll_intensity": 6,
    "pinch_distance_start": 0.065,
    "zoom_step_distance": 0.018,
    "tremor_strength": 70,
    "cursor_gain": 1.55,
}


def load_config() -> dict:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        merged = {**DEFAULTS, **data}
        if "tremor_strength" not in data and "tremor_filter" in data:
            merged["tremor_strength"] = 70 if bool(data["tremor_filter"]) else 0
        return merged
    except (OSError, json.JSONDecodeError, TypeError):
        return DEFAULTS.copy()


def save_config(values: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(values, indent=2), encoding="utf-8")


def main() -> None:
    config = load_config()
    root = tk.Tk()
    root.title("AETHER | Configurações")
    root.geometry("540x760")
    root.minsize(500, 700)
    root.configure(bg="#0b1020")

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TScale", background="#111a30", troughcolor="#263451")

    shell = tk.Frame(root, bg="#0b1020", padx=24, pady=22)
    shell.pack(fill="both", expand=True)

    tk.Label(shell, text="AETHER", bg="#0b1020", fg="#7c9cff", font=("Segoe UI", 22, "bold")).pack(anchor="w")
    tk.Label(shell, text="Painel de controle", bg="#0b1020", fg="#f3f6ff", font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(2, 3))
    tk.Label(
        shell,
        text="Faixas ampliadas para ajustar o AETHER à sua câmera e ao seu jeito de mover as mãos.",
        bg="#0b1020",
        fg="#9eaccb",
        font=("Segoe UI", 9),
        wraplength=470,
        justify="left",
    ).pack(anchor="w", pady=(0, 16))

    panel = tk.Frame(shell, bg="#111a30", padx=18, pady=14, highlightthickness=1, highlightbackground="#253454")
    panel.pack(fill="both", expand=True)

    threshold_var = tk.DoubleVar(value=float(config["scroll_threshold"]))
    intensity_var = tk.IntVar(value=int(config["scroll_intensity"]))
    pinch_var = tk.DoubleVar(value=float(config["pinch_distance_start"]))
    zoom_var = tk.DoubleVar(value=float(config["zoom_step_distance"]))
    tremor_var = tk.IntVar(value=int(config["tremor_strength"]))
    gain_var = tk.DoubleVar(value=float(config["cursor_gain"]))
    status_var = tk.StringVar(value="Configurações carregadas")

    value_labels: dict[str, tk.StringVar] = {
        "scroll": tk.StringVar(),
        "intensity": tk.StringVar(),
        "pinch": tk.StringVar(),
        "zoom": tk.StringVar(),
        "tremor": tk.StringVar(),
        "gain": tk.StringVar(),
    }

    def update_labels(*_args) -> None:
        value_labels["scroll"].set(f"{threshold_var.get():.3f}")
        value_labels["intensity"].set(str(int(round(intensity_var.get()))))
        value_labels["pinch"].set(f"{pinch_var.get():.3f}")
        value_labels["zoom"].set(f"{zoom_var.get():.3f}")
        value_labels["tremor"].set(f"{int(round(tremor_var.get()))}%")
        value_labels["gain"].set(f"{gain_var.get():.2f}x")

    def current_values() -> dict:
        return {
            "scroll_threshold": round(float(threshold_var.get()), 4),
            "scroll_intensity": int(round(intensity_var.get())),
            "pinch_distance_start": round(float(pinch_var.get()), 4),
            "zoom_step_distance": round(float(zoom_var.get()), 4),
            "tremor_strength": int(round(tremor_var.get())),
            "cursor_gain": round(float(gain_var.get()), 2),
        }

    def persist(*_args) -> None:
        update_labels()
        try:
            save_config(current_values())
            status_var.set("✓ Ajustes salvos e aplicados")
        except OSError as exc:
            status_var.set(f"Não foi possível salvar: {exc}")

    def section(
        label: str,
        variable: tk.Variable,
        value_label: tk.StringVar,
        from_: float,
        to: float,
        hint: str,
        min_text: str,
        max_text: str,
    ) -> None:
        head = tk.Frame(panel, bg="#111a30")
        head.pack(fill="x", pady=(7, 0))
        tk.Label(head, text=label, bg="#111a30", fg="#f3f6ff", font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Label(head, textvariable=value_label, bg="#111a30", fg="#8ba8ff", font=("Consolas", 10, "bold")).pack(side="right")
        tk.Label(panel, text=hint, bg="#111a30", fg="#9eaccb", font=("Segoe UI", 8), wraplength=440, justify="left").pack(anchor="w", pady=(2, 0))
        ttk.Scale(panel, variable=variable, from_=from_, to=to, orient="horizontal", command=lambda _v: persist()).pack(fill="x", pady=(4, 0))
        limits = tk.Frame(panel, bg="#111a30")
        limits.pack(fill="x", pady=(0, 4))
        tk.Label(limits, text=min_text, bg="#111a30", fg="#667797", font=("Segoe UI", 8)).pack(side="left")
        tk.Label(limits, text=max_text, bg="#111a30", fg="#667797", font=("Segoe UI", 8)).pack(side="right")

    update_labels()
    section("Sensibilidade do scroll", threshold_var, value_labels["scroll"], 0.002, 0.060,
            "Menor = responde a movimentos menores. Maior = exige um movimento mais amplo.", "0.002 (muito sensível)", "0.060 (pouco sensível)")
    section("Intensidade do scroll", intensity_var, value_labels["intensity"], 1, 30,
            "Quantidade de rolagem executada por cada disparo.", "1", "30")
    section("Sensibilidade da pinça", pinch_var, value_labels["pinch"], 0.045, 0.100,
            "Maior = polegar e indicador podem ficar um pouco mais separados e ainda contar como pinça.", "0.045", "0.100")
    section("Sensibilidade do zoom", zoom_var, value_labels["zoom"], 0.010, 0.060,
            "Menor = menos movimento vertical da pinça para cada passo de zoom.", "0.010 (mais sensível)", "0.060")
    section("Estabilização do cursor", tremor_var, value_labels["tremor"], 0, 100,
            "0% prioriza resposta imediata; 100% prioriza estabilidade. O filtro continua liberando movimentos rápidos.", "0%", "100%")
    section("Alcance do cursor", gain_var, value_labels["gain"], 1.0, 2.2,
            "Aumenta a distância percorrida na tela sem exigir movimentos maiores do braço.", "1.00x", "2.20x")

    for variable in (threshold_var, intensity_var, pinch_var, zoom_var, tremor_var, gain_var):
        variable.trace_add("write", update_labels)

    tk.Label(shell, textvariable=status_var, bg="#0b1020", fg="#8fe0c1", font=("Segoe UI", 9)).pack(anchor="w", pady=(12, 7))
    tk.Button(
        shell,
        text="Salvar configurações",
        command=persist,
        bg="#5478ff",
        fg="white",
        activebackground="#6b89ff",
        activeforeground="white",
        relief="flat",
        font=("Segoe UI", 10, "bold"),
        padx=12,
        pady=9,
        cursor="hand2",
    ).pack(fill="x")

    root.mainloop()


if __name__ == "__main__":
    main()
