"""5분 후 알람 봇 GUI 애플리케이션.

사용자가 블로그 URL을 입력하면 제목을 크롤링하여 리스트에 저장하고,
5분 후 팝업 알람으로 읽기 알림을 띄워준다.
"""
from __future__ import annotations

import threading
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from tkinter import messagebox
from typing import List, Optional

import requests
from bs4 import BeautifulSoup


ALARM_DELAY_SECONDS = 5 * 60
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass
class AlarmEntry:
    """등록된 알람 정보를 저장하는 데이터 클래스."""

    title: str
    url: str
    scheduled_time: datetime
    timer: Optional[threading.Timer] = field(default=None, repr=False)


class AlarmBotApp:
    """5분 후 알람 봇 Tkinter 애플리케이션."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("5분 후 알람 봇")

        self.url_var = tk.StringVar()
        self.status_var = tk.StringVar()

        self.entries: List[AlarmEntry] = []
        self._listbox_job: Optional[str] = None

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # UI 구성 ---------------------------------------------------------------
    def _build_ui(self) -> None:
        root = self.root

        input_frame = tk.Frame(root)
        input_frame.pack(fill=tk.X, padx=12, pady=(12, 4))

        url_entry = tk.Entry(input_frame, textvariable=self.url_var)
        url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        url_entry.bind("<Return>", lambda _event: self.register_url())

        add_button = tk.Button(input_frame, text="등록", command=self.register_url)
        add_button.pack(side=tk.LEFT, padx=(8, 0))

        list_frame = tk.Frame(root)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 4))

        list_label = tk.Label(list_frame, text="등록된 제목 리스트 (최신 순)")
        list_label.pack(anchor=tk.W)

        self.listbox = tk.Listbox(list_frame, height=10)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=(4, 0))

        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.configure(yscrollcommand=scrollbar.set)

        status_label = tk.Label(root, textvariable=self.status_var, anchor=tk.W, fg="gray")
        status_label.pack(fill=tk.X, padx=12, pady=(0, 12))

    # 이벤트 처리 -----------------------------------------------------------
    def register_url(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            self._set_status("URL을 입력해 주세요.")
            return

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        self._set_status("제목을 가져오는 중...")
        self.root.update_idletasks()

        try:
            title = self._fetch_title(url)
        except ValueError as exc:
            self._set_status(str(exc))
            return

        scheduled_time = datetime.now() + timedelta(seconds=ALARM_DELAY_SECONDS)
        entry = AlarmEntry(title=title, url=url, scheduled_time=scheduled_time)
        self.entries.insert(0, entry)
        self._refresh_listbox()
        self._ensure_listbox_updates()
        self.url_var.set("")

        timer = threading.Timer(ALARM_DELAY_SECONDS, self._trigger_alarm, args=(entry,))
        timer.daemon = True
        entry.timer = timer
        timer.start()

        self._set_status(f"'{title}' 알람이 등록되었습니다. 5분 후 알림이 울립니다.")

    def _trigger_alarm(self, entry: AlarmEntry) -> None:
        """타이머가 만료되면 메인 스레드에서 팝업을 띄운다."""

        def show_popup() -> None:
            messagebox.showinfo("⏰ 읽을 시간입니다!", f"읽을 글: {entry.title}")
            self._set_status(f"'{entry.title}' 알람이 울렸습니다.")

        self.root.after(0, show_popup)

    # 데이터 처리 -----------------------------------------------------------
    def _fetch_title(self, url: str) -> str:
        try:
            response = requests.get(url, timeout=10, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ValueError(f"링크를 불러오지 못했습니다: {exc}") from exc

        soup = BeautifulSoup(response.text, "html.parser")

        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            return title_tag.string.strip()

        og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "title"})
        if og_title and og_title.get("content"):
            return og_title["content"].strip()

        raise ValueError("제목을 찾을 수 없습니다. 다른 링크를 시도해 주세요.")

    def _refresh_listbox(self) -> None:
        self.listbox.delete(0, tk.END)
        for entry in self.entries:
            remaining = max(int((entry.scheduled_time - datetime.now()).total_seconds()), 0)
            minutes, seconds = divmod(remaining, 60)
            eta = entry.scheduled_time.strftime("%H:%M:%S")
            display_text = (
                f"{entry.title} (알림 예정: {eta}, 남은 시간: {minutes:02d}:{seconds:02d})"
            )
            self.listbox.insert(tk.END, display_text)

    def _ensure_listbox_updates(self) -> None:
        if self.entries and self._listbox_job is None:
            self._schedule_next_update()

    def _schedule_next_update(self) -> None:
        self._listbox_job = self.root.after(1000, self._on_listbox_tick)

    def _on_listbox_tick(self) -> None:
        self._listbox_job = None
        self._refresh_listbox()
        if self.entries:
            self._schedule_next_update()

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    def on_close(self) -> None:
        for entry in self.entries:
            if entry.timer:
                entry.timer.cancel()
        if self._listbox_job is not None:
            self.root.after_cancel(self._listbox_job)
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = AlarmBotApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
