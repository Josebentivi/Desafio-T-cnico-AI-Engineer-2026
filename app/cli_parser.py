from __future__ import annotations

import argparse
import sys


class PortugueseArgumentParser(argparse.ArgumentParser):
    def format_help(self) -> str:
        return (
            super().format_help()
            .replace("usage:", "uso:", 1)
            .replace("positional arguments:", "argumentos posicionais:")
            .replace("options:", "opções:")
            .replace("show this help message and exit", "mostrar esta ajuda e sair")
        )

    def format_usage(self) -> str:
        return super().format_usage().replace("usage:", "uso:", 1)

    def error(self, message: str) -> None:
        translations = {
            "the following arguments are required:": "os seguintes argumentos são obrigatórios:",
            "unrecognized arguments:": "argumentos não reconhecidos:",
            "invalid choice:": "opção inválida:",
            "(choose from": "(escolha entre",
            "expected one argument": "é necessário informar um valor",
            "argument ": "argumento ",
        }
        for source, target in translations.items():
            message = message.replace(source, target)
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: erro: {message}\n")
