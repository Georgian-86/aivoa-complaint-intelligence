import os
import tempfile

import pytest

# Point the app at a throwaway database before any app module is imported.
_TMP = tempfile.mkdtemp(prefix="aivoa-test-")
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_TMP}/test.db"
os.environ["GROQ_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def particulate_email() -> str:
    return """
From: Priya Raghavan <qa@meridianpharma.example>
Subject: URGENT - Particulate matter in Ceftrioxam 1g Injection
Date: 14 September 2026

We are writing on behalf of Meridian Pharma Distribution, Hyderabad.

On 12 September 2026, our warehouse QA team identified black fibrous
particulate matter visible in the reconstituted solution of multiple vials.

  Product Name : Ceftrioxam 1 g Injection
  Batch No.    : CFX24B902
  Mfg. Date    : 03/2025
  Exp. Date    : 02/2027

Quantity affected: 38 vials.

A patient receiving this product required hospitalisation for observation.
The affected vials are available for collection.
"""
