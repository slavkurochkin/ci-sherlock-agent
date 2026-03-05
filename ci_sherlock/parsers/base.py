from abc import ABC, abstractmethod
from ci_sherlock.models import TestResult


class BaseParser(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def parse(self, report_path: str) -> list[TestResult]:
        """
        Read the report at report_path and return a flat list of TestResult.
        Raises FileNotFoundError if the file doesn't exist.
        Raises ValueError if the file is not a valid report for this parser.
        """
        ...
