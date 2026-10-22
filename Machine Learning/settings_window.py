from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import ttk

CONFIG_PATH = Path(__file__).resolve().parents[2] / "aether_settings.json"
DEFAULTS = {"scroll_threshold": 0.012, "scroll_intensity": 6, "tremor_filter": True}


def load_config() -> dict:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return {**DEFAULTS, **data}
    except (OSError, json.JSONDecodeError, TypeError):
        return DEFAULTS.copy()


def save_config(values: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(values, indent=2), encoding="utf-8")


def main() -> None:
    config = load_config()
    root = tk.Tk()
    root.title("AETHER | Configurações")
    root.geometry("480x510")
    root.minsize(440, 480)
    root.configure(bg="#0b1020")

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TScale", background="#111a30", troughcolor="#263451")
    style.configure("TCheckbutton", background="#111a30", foreground="#e7edff", font=("Segoe UI", 10))

    shell = tk.Frame(root, bg="#0b1020", padx=24, pady=22)
    shell.pack(fill="both", expand=True)
    tk.Label(shell, text="AETHER", bg="#0b1020", fg="#7c9cff", font=("Segoe UI", 22, "bold")).pack(anchor="w")
    tk.Label(shell, text="Painel de sensibilidade", bg="#0b1020", fg="#f3f6ff", font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(2, 3))
    tk.Label(shell, text="Os ajustes são aplicados enquanto o controle estiver aberto.", bg="#0b1020", fg="#9eaccb", font=("Segoe UI", 9), wraplength=410, justify="left").pack(anchor="w", pady=(0, 18))

    panel = tk.Frame(shell, bg="#111a30", padx=18, pady=16, highlightthickness=1, highlightbackground="#253454")
    panel.pack(fill="x")

    threshold_var = tk.DoubleVar(value=float(config["scroll_threshold"]))
    intensity_var = tk.IntVar(value=int(config["scroll_intensity"]))
    tremor_var = tk.BooleanVar(value=bool(config["tremor_filter"]))
    threshold_value = tk.StringVar()
    intensity_value = tk.StringVar()
    status_var = tk.StringVar(value="Configurações carregadas")

    def update_labels(*_args):
        threshold_value.set(f"{threshold_var.get():.3f}")
        intensity_value.set(str(intensity_var.get()))

    save_job = {"id": None}

    def persist(*_args):
        values = {
            "scroll_threshold": round(float(threshold_var.get()), 3),
            "scroll_intensity": max(1, min(15, round(float(intensity_var.get())))),
            "tremor_filter": bool(tremor_var.get()),
        }
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            temp_path = CONFIG_PATH.with_suffix(".json.tmp")
            temp_path.write_text(json.dumps(values, indent=2), encoding="utf-8")
            temp_path.replace(CONFIG_PATH)
            status_var.set(f"✓ Salvo: {CONFIG_PATH.name}")
        except (OSError, tk.TclError, ValueError) as exc:
            status_var.set(f"Não foi possível salvar: {exc}")

    def schedule_persist(*_args):
        if save_job["id"] is not None:
            root.after_cancel(save_job["id"])
        save_job["id"] = root.after(150, persist)

    def section(label: str, variable, value_label: tk.StringVar, from_: float, to: float, resolution: float, hint: str):
        head = tk.Frame(panel, bg="#111a30")
        head.pack(fill="x", pady=(5, 0))
        tk.Label(head, text=label, bg="#111a30", fg="#f3f6ff", font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Label(head, textvariable=value_label, bg="#111a30", fg="#8ba8ff", font=("Consolas", 10, "bold")).pack(side="right")
        tk.Label(panel, text=hint, bg="#111a30", fg="#9eaccb", font=("Segoe UI", 9), wraplength=390, justify="left").pack(anchor="w", pady=(3, 0))
        ttk.Scale(panel, variable=variable, from_=from_, to=to, orient="horizontal", command=schedule_persist).pack(fill="x", pady=(5, 7))

    update_labels()
    section("Sensibilidade do scroll", threshold_var, threshold_value, 0.004, 0.030, 0.001, "Mais à esquerda = reage com movimentos menores. Mais à direita = exige movimento maior.")
    section("Intensidade do scroll", intensity_var, intensity_value, 1, 15, 1, "Define quantas unidades a página avança em cada gesto.")

    check = ttk.Checkbutton(panel, text="Reduzir tremores do cursor", variable=tremor_var, command=schedule_persist)
    check.pack(anchor="w", pady=(9, 3))
    tk.Label(panel, text="Pode deixar o cursor mais estável, com uma resposta um pouco mais suave.", bg="#111a30", fg="#9eaccb", font=("Segoe UI", 9), wraplength=390, justify="left").pack(anchor="w")

    threshold_var.trace_add("write", update_labels)
    intensity_var.trace_add("write", update_labels)
    tk.Label(shell, textvariable=status_var, bg="#0b1020", fg="#8fe0c1", font=("Segoe UI", 9)).pack(anchor="w", pady=(14, 8))
    tk.Button(shell, text="Salvar configurações", command=persist, bg="#5478ff", fg="white", activebackground="#6b89ff", activeforeground="white", relief="flat", font=("Segoe UI", 10, "bold"), padx=12, pady=10, cursor="hand2").pack(fill="x")
    tk.Label(shell, text=f"Arquivo: {CONFIG_PATH}", bg="#0b1020", fg="#7584a5", font=("Segoe UI", 8), wraplength=410, justify="left").pack(anchor="w", pady=(8, 0))
    tk.Label(shell, text="Feche esta janela para manter o AETHER rodando sem o painel.", bg="#0b1020", fg="#7584a5", font=("Segoe UI", 8)).pack(anchor="w", pady=(6, 0))
    root.mainloop()


if __name__ == "__main__":
    main()
