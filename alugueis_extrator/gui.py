"""Tkinter desktop interface for the local rental-statement extractor."""

from __future__ import annotations

import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .app_version import APP_VERSION
from .application_service import (
    count_pdf_files,
    normalize_competence,
    run_application_batch,
)
from .gui_presentation import friendly_issue, friendly_warning, result_summary


class RentalExtractorWindow:
    def __init__(
        self,
        root: tk.Tk,
        *,
        initial_folder: str | None = None,
        initial_competence: str | None = None,
        automation_run: bool = False,
        automation_close: bool = False,
    ) -> None:
        self.root = root
        self.root.title(f"Extrator de Demonstrativos de Aluguel — v{APP_VERSION}")
        self.root.geometry("780x650")
        self.root.minsize(680, 570)
        self.root.columnconfigure(0, weight=1)

        self.events: queue.Queue[tuple] = queue.Queue()
        self.folder_path: Path | None = None
        self.pdf_count = 0
        self.busy = False
        self.automation_run = automation_run
        self.automation_close = automation_close

        self.folder_var = tk.StringVar(value="")
        self.pdf_count_var = tk.StringVar(value="Selecione a pasta dos demonstrativos.")
        self.period_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Aguardando seleção da pasta.")
        self.output_var = tk.StringVar(value="")

        self._build_widgets()
        self.root.after(100, self._poll_events)
        if initial_competence:
            self.period_var.set(initial_competence)
        if initial_folder:
            self.root.after(0, lambda: self._count_selected_folder(initial_folder))

    def _build_widgets(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        main = ttk.Frame(self.root, padding=(26, 22, 26, 20))
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(7, weight=1)

        ttk.Label(
            main,
            text="Extrator de Demonstrativos de Aluguel",
            font=("Segoe UI", 19, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            main,
            text="Exporte os dados dos demonstrativos de aluguel em poucos cliques.",
            font=("Segoe UI", 10),
        ).grid(row=1, column=0, sticky="w", pady=(4, 20))

        folder_group = ttk.LabelFrame(main, text="Pasta dos demonstrativos", padding=14)
        folder_group.grid(row=2, column=0, sticky="ew")
        folder_group.columnconfigure(0, weight=1)
        self.folder_entry = ttk.Entry(
            folder_group, textvariable=self.folder_var, state="readonly"
        )
        self.folder_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.select_button = ttk.Button(
            folder_group, text="Selecionar pasta...", command=self._select_folder
        )
        self.select_button.grid(row=0, column=1)
        ttk.Label(folder_group, textvariable=self.pdf_count_var).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )

        period_group = ttk.LabelFrame(main, text="Competência (opcional)", padding=14)
        period_group.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        period_group.columnconfigure(0, weight=1)
        self.period_entry = ttk.Entry(
            period_group, textvariable=self.period_var, width=14
        )
        self.period_entry.grid(row=0, column=0, sticky="w")
        ttk.Label(
            period_group,
            text="Use MM/AAAA, por exemplo 09/2026. Em branco: Relatorio_Alugueis.xlsx.",
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))

        actions = ttk.Frame(main)
        actions.grid(row=4, column=0, sticky="ew", pady=(18, 12))
        self.generate_button = ttk.Button(
            actions,
            text="Gerar relatório",
            command=self._start_processing,
            state="disabled",
            style="Accent.TButton",
        )
        self.generate_button.grid(row=0, column=0, sticky="w")
        ttk.Label(actions, textvariable=self.status_var).grid(
            row=0, column=1, sticky="w", padx=(16, 0)
        )

        self.summary_frame = ttk.LabelFrame(main, text="Resultado", padding=14)
        self.summary_frame.grid(row=5, column=0, sticky="ew")
        self.summary_frame.columnconfigure(0, weight=1)
        self.summary_label = ttk.Label(
            self.summary_frame,
            text="O resumo do processamento aparecerá aqui.",
            justify="left",
            font=("Segoe UI", 10),
        )
        self.summary_label.grid(row=0, column=0, sticky="w")
        self.output_label = ttk.Label(
            self.summary_frame, textvariable=self.output_var, font=("Segoe UI", 9)
        )
        self.output_label.grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.open_folder_button = ttk.Button(
            self.summary_frame,
            text="Abrir pasta do relatório",
            command=self._open_output_folder,
            state="disabled",
        )
        self.open_folder_button.grid(row=1, column=1, sticky="e", padx=(12, 0))

        detail_group = ttk.LabelFrame(main, text="Erros e avisos", padding=10)
        detail_group.grid(row=7, column=0, sticky="nsew", pady=(14, 0))
        detail_group.columnconfigure(0, weight=1)
        detail_group.rowconfigure(0, weight=1)
        self.details = tk.Text(
            detail_group,
            height=8,
            wrap="word",
            state="disabled",
            font=("Segoe UI", 9),
            relief="flat",
            background="#f5f7fa",
        )
        self.details.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(detail_group, orient="vertical", command=self.details.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.details.configure(yscrollcommand=scrollbar.set)

        ttk.Label(
            main,
            text="Os PDFs com dados ausentes ou ambíguos ficam fora do Excel e aparecem para revisão.",
            font=("Segoe UI", 9),
        ).grid(row=8, column=0, sticky="w", pady=(12, 0))

    def _set_controls_busy(self, busy: bool) -> None:
        self.busy = busy
        self.select_button.configure(state="disabled" if busy else "normal")
        self.period_entry.configure(state="disabled" if busy else "normal")
        can_generate = not busy and self.folder_path is not None and self.pdf_count > 0
        self.generate_button.configure(state="normal" if can_generate else "disabled")

    def _select_folder(self) -> None:
        selected = filedialog.askdirectory(
            parent=self.root,
            title="Selecione a pasta dos demonstrativos em PDF",
            mustexist=True,
        )
        if not selected:
            return
        self._count_selected_folder(selected)

    def _count_selected_folder(self, selected: str | Path) -> None:
        self.folder_path = Path(selected)
        self.folder_var.set(str(selected))
        self.pdf_count = 0
        self.pdf_count_var.set("Contando PDFs na pasta e nas subpastas...")
        self.status_var.set("Verificando a pasta...")
        self.output_var.set("")
        self.open_folder_button.configure(state="disabled")
        self._set_controls_busy(True)
        threading.Thread(
            target=self._count_worker,
            args=(self.folder_path,),
            name="pdf-count",
            daemon=True,
        ).start()

    def _count_worker(self, folder: Path) -> None:
        try:
            self.events.put(("count", folder, count_pdf_files(folder), None))
        except Exception as exc:
            self.events.put(("count", folder, None, exc))

    def _start_processing(self) -> None:
        if self.busy or self.folder_path is None:
            return
        try:
            normalize_competence(self.period_var.get())
        except ValueError as exc:
            messagebox.showwarning("Competência inválida", str(exc), parent=self.root)
            self.period_entry.focus_set()
            return
        if self.pdf_count == 0:
            messagebox.showinfo(
                "Nenhum PDF encontrado",
                "Selecione uma pasta que contenha demonstrativos em PDF.",
                parent=self.root,
            )
            return

        folder = self.folder_path
        competence = self.period_var.get()
        self._set_controls_busy(True)
        self.status_var.set(f"Processando {self.pdf_count} PDFs. A janela continuará responsiva.")
        self.summary_label.configure(text="Processamento em andamento...")
        self.output_var.set("")
        self.open_folder_button.configure(state="disabled")
        self._set_details("")
        threading.Thread(
            target=self._batch_worker,
            args=(folder, competence),
            name="rental-batch",
            daemon=True,
        ).start()

    def _batch_worker(self, folder: Path, competence: str) -> None:
        try:
            self.events.put(("batch", run_application_batch(folder, competence), None))
        except Exception as exc:
            self.events.put(("batch", None, exc))

    def _poll_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "count":
                    _, folder, count, error = event
                    if folder != self.folder_path:
                        continue
                    self._set_controls_busy(False)
                    if error is not None:
                        self.pdf_count_var.set("Não foi possível ler esta pasta.")
                        self.status_var.set("Selecione uma pasta válida.")
                        messagebox.showerror(
                            "Pasta indisponível",
                            "Não foi possível contar os PDFs nesta pasta.",
                            parent=self.root,
                        )
                    else:
                        self.pdf_count = count
                        self.pdf_count_var.set(
                            f"{count} PDF(s) encontrado(s), incluindo subpastas."
                        )
                        self.status_var.set(
                            "Pronto para processar." if count else "Nenhum PDF encontrado."
                        )
                        self._set_controls_busy(False)
                        if self.automation_run and count:
                            self.automation_run = False
                            self.root.after(0, self._start_processing)
                elif event[0] == "batch":
                    _, application_run, error = event
                    self._set_controls_busy(False)
                    if error is not None:
                        self.status_var.set("Não foi possível gerar o relatório.")
                        messagebox.showerror(
                            "Falha ao gerar relatório",
                            "O relatório não foi concluído. Verifique se a pasta permite gravação e tente novamente.",
                            parent=self.root,
                        )
                        continue
                    self._show_result(application_run)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _show_result(self, application_run) -> None:
        report = application_run.report
        self.summary_label.configure(text=result_summary(report))
        self.output_var.set(f"Arquivo: {report.output_path.name}")
        self.open_folder_button.configure(state="normal")
        self.status_var.set(
            "Concluído com documentos para revisão."
            if report.errors
            else "Relatório gerado com sucesso."
        )
        lines: list[str] = []
        for issue in report.errors:
            lines.extend((issue.file, friendly_issue(issue), ""))
        for warning in report.warnings:
            lines.extend((warning.file, friendly_warning(warning), ""))
        if application_run.log_error:
            lines.extend(
                (
                    "",
                    "A planilha foi gerada, mas o log legível não pôde ser salvo. Os diagnósticos JSON foram preservados.",
                )
            )
        self._set_details("\n".join(lines).strip())
        if self.automation_close:
            self.root.after(1000, self.root.destroy)

    def _set_details(self, text: str) -> None:
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def _open_output_folder(self) -> None:
        if self.folder_path is None:
            return
        try:
            if hasattr(os, "startfile"):
                os.startfile(str(self.folder_path))
            else:
                raise OSError("A abertura de pastas está disponível na versão Windows.")
        except OSError:
            messagebox.showerror(
                "Não foi possível abrir a pasta",
                "Abra manualmente a pasta selecionada para localizar o Excel.",
                parent=self.root,
            )


def main(
    *,
    initial_folder: str | None = None,
    initial_competence: str | None = None,
    automation_run: bool = False,
    automation_close: bool = False,
) -> None:
    root = tk.Tk()
    RentalExtractorWindow(
        root,
        initial_folder=initial_folder,
        initial_competence=initial_competence,
        automation_run=automation_run,
        automation_close=automation_close,
    )
    root.mainloop()


if __name__ == "__main__":
    main()
