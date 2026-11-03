from us_treasury_api import USTreasuryAPI
from bce_bond_api import BCEBondAPI
from bond_normalizer import BondNormalizer


entrada = {
    "ticker": "ES10Y",
    "type": "bond",
    "api": "bce",
    "start_date": "2025-10-01",
    "end_date": "2026-10-30",
}

fetchers = {
    "us_treasury": USTreasuryAPI,
    "bce": BCEBondAPI,
}

if entrada["type"] != "bond":
    raise ValueError(
        "Este ejemplo solo admite el tipo bond."
    )

if entrada["api"] not in fetchers:
    raise ValueError("API no admitida.")

# 1. Descargar los datos originales.
fetcher = fetchers[entrada["api"]]()

datos_originales = fetcher.get_data(
    ticker=entrada["ticker"],
    start_date=entrada["start_date"],
    end_date=entrada["end_date"],
)

# 2. Normalizar y construir los objetos.
normalizer = BondNormalizer()

bono = normalizer.normalize(
    data=datos_originales,
    ticker=entrada["ticker"],
    source=entrada["api"],
    start_date=entrada["start_date"],
    end_date=entrada["end_date"],
)

# 3. Mostrar el resultado.
if bono is None:
    print(
        "No hay datos para la referencia "
        "y fechas solicitadas."
    )

else:
    print(bono.name)
    print(f"Identificador: {bono.ticker}")
    print(f"País: {bono.country}")
    print(f"Plazo en años: {bono.maturity_years}")
    print(f"Fuente: {bono.source}")

    print("\nHistórico de rentabilidades (%):")
    print(bono.series.ytm)

    print(
        f"\nTotal de observaciones: "
        f"{len(bono.series.ytm)}"
    )

    print(
        f"Última rentabilidad: "
        f"{bono.series.current_yield():.3f} %"
    )

    print(
        "\nCambios entre observaciones "
        "en puntos básicos:"
    )

    print(bono.series.yield_change_bps().tail())