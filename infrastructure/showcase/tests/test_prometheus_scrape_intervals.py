from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "prometheus" / "prometheus.yml"


def _job_block(text: str, job: str) -> str:
    marker = f"  - job_name: {job}\n"
    start = text.index(marker)
    next_job = text.find("\n  - job_name:", start + len(marker))
    return text[start:] if next_job == -1 else text[start:next_job]


def test_expensive_database_backed_exporters_are_not_scraped_globally() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    expected = {
        "jason-usage-attribution": ("2m", "30s"),
        "jason-reflection": ("1m", "15s"),
        "jason-security-control": ("1m", "15s"),
        "jason-autonomy-flight-recorder": ("1m", "15s"),
    }
    for job, (interval, timeout) in expected.items():
        block = _job_block(text, job)
        assert f"    scrape_interval: {interval}\n" in block
        assert f"    scrape_timeout: {timeout}\n" in block
