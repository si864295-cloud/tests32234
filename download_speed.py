#!/usr/bin/env python3
"""Измерение скорости скачивания по HTTP/HTTPS без внешних зависимостей."""

import argparse
from collections.abc import Sequence
import http.client
import math
import statistics
import sys
import time
from typing import Final, cast
import urllib.error
import urllib.parse
import urllib.request


BLOCK_SIZE: Final[int] = 256 * 1024


class Arguments(argparse.Namespace):
    """Типизированные значения аргументов командной строки."""

    url: str
    attempts: int
    timeout: float


def positive_int(value: str) -> int:
    try:
        number: int = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("нужно целое число больше нуля") from None
    if number <= 0:
        raise argparse.ArgumentTypeError("нужно целое число больше нуля")
    return number


def positive_timeout(value: str) -> float:
    try:
        number: float = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("нужно конечное число больше нуля") from None
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("нужно конечное число больше нуля")
    return number


def http_url(value: str) -> str:
    try:
        parsed: urllib.parse.SplitResult = urllib.parse.urlsplit(value)
        valid: bool = parsed.scheme in ("http", "https") and bool(parsed.hostname)
        parsed.port  # Проверить корректность номера порта, если он указан.
    except ValueError:
        valid = False
    if not valid:
        raise argparse.ArgumentTypeError("нужен URL http:// или https:// с именем хоста")
    return value


def download(url: str, timeout: float) -> tuple[int, float]:
    request: urllib.request.Request = urllib.request.Request(
        url,
        headers={"Cache-Control": "no-cache", "Accept-Encoding": "identity"},
    )
    received: int = 0
    started: float = time.perf_counter()
    # URL ограничен HTTP/HTTPS; для них urlopen возвращает HTTPResponse.
    with cast(http.client.HTTPResponse, urllib.request.urlopen(request, timeout=timeout)) as response:
        length: str | None = response.headers.get("Content-Length")
        expected: int | None = None
        if length is not None:
            try:
                expected = int(length)
                if expected < 0:
                    raise ValueError
            except ValueError:
                raise ValueError("сервер вернул некорректный Content-Length") from None
        block: bytes
        while True:
            block = response.read(BLOCK_SIZE)
            if not block:
                break
            received += len(block)
        elapsed: float = max(time.perf_counter() - started, 1e-9)
        if expected is not None and received < expected:
            raise OSError(f"неполная загрузка: получено {received} из {expected} байт")
    return received, elapsed


def format_speed(bytes_per_second: float) -> str:
    return (
        f"{bytes_per_second * 8 / 1_000_000:.2f} Мбит/с"
        f" ({bytes_per_second / 1_048_576:.2f} МиБ/с)"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=(
            "Измеряет скорость скачивания с конкретного URL. "
            "Запросы выполняются последовательно, каждый ответ скачивается полностью. "
            "Данные читаются блоками без сохранения на диск. "
            "Время включает установление соединения и ожидание ответа сервера. "
            "Итог: общее и среднее время запросов, общий объём данных. "
            "В итогах учитываются только успешные полные загрузки."
        )
    )
    parser.add_argument("--url", required=True, type=http_url, help="адрес файла по HTTP/HTTPS")
    parser.add_argument(
        "--attempts", type=positive_int, default=10,
        help="количество последовательных загрузок (по умолчанию: 10)",
    )
    parser.add_argument(
        "--timeout", type=positive_timeout, default=30.0,
        help=(
            "таймаут отдельной сетевой операции в секундах "
            "(по умолчанию: 30); не ограничивает общее время загрузки"
        ),
    )
    args: Arguments = parser.parse_args(argv, namespace=Arguments())
    durations: list[float] = []
    total_bytes: int = 0
    failures: int = 0
    attempt: int
    size: int
    elapsed: float
    try:
        for attempt in range(1, args.attempts + 1):
            try:
                size, elapsed = download(args.url, args.timeout)
            except (OSError, urllib.error.URLError, http.client.HTTPException, ValueError) as error:
                failures += 1
                print(f"[{attempt}/{args.attempts}] Ошибка: {error}", file=sys.stderr, flush=True)
                continue
            speed: float = size / elapsed
            durations.append(elapsed)
            total_bytes += size
            print(
                f"[{attempt}/{args.attempts}] {size} байт ({size / 1_048_576:.2f} МиБ), "
                f"{elapsed:.3f} с, {format_speed(speed)}",
                flush=True,
            )
    except KeyboardInterrupt:
        print("\nПрервано пользователем.", file=sys.stderr)
        return 130

    print(f"Итого: успешных загрузок — {len(durations)}, ошибок — {failures}.", flush=True)
    print("Итоговые показатели учитывают только успешные полные загрузки.")
    print(f"Общее время запросов: {sum(durations):.3f} с")
    if durations:
        print(f"Среднее время запроса: {statistics.mean(durations):.3f} с")
    else:
        print("Среднее время запроса: недоступно (нет успешных загрузок)")
    print(f"Общий объём скачанных данных: {total_bytes} байт ({total_bytes / 1_048_576:.2f} МиБ)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
