from us_treasury_api import USTreasuryAPI
from bce_bond_api import BCEBondAPI
from jp_bond_api import JapanBondAPI
from uk_bond_api import UKBondAPI
from bond_normalizer import BondNormalizer


entrada = {
    "ticker": "JP10Y",
    "type": "bond",
    "api": "japan",
    "start_date": "2025-10-01",
    "end_date": "2026-10-30",
}

fetchers = {
    "us_treasury": USTreasuryAPI,
    "bce": BCEBondAPI,
    "japan": JapanBondAPI,
    "uk": UKBondAPI,
}

if entrada["type"] != "bond":
    raise ValueError(
        "Este ejemplo solo admite el tipo bond."
    )

if entrada["api"] not in fetchers:
    raise ValueError("API no admitida.")

# 1. Crear el fetcher de la fuente elegida.
fetcher = fetchers[entrada["api"]]()

# 2. Descargar los datos originales.
datos_originales = fetcher.get_data(
    ticker=entrada["ticker"],
    start_date=entrada["start_date"],
    end_date=entrada["end_date"],
)

# 3. Normalizar, limpiar y construir el objeto Bond.
normalizer = BondNormalizer()

bono = normalizer.normalize(
    data=datos_originales,
    ticker=entrada["ticker"],
    source=entrada["api"],
    start_date=entrada["start_date"],
    end_date=entrada["end_date"],
)

# 4. Mostrar la información del objeto.
print(bono.name)
print(f"Identificador: {bono.ticker}")
print(f"País o zona: {bono.country}")
print(f"Plazo en años: {bono.maturity_years}")
print(f"Fuente: {bono.source}")

print("\nHistórico de rentabilidades (%):")
print(bono.series.ytm)

print(
    f"\nTotal de observaciones: "
    f"{len(bono.series.ytm)}"
)

print(
    f"Primera fecha: "
    f"{bono.series.date[0]:%Y-%m-%d}"
)

print(
    f"Última fecha: "
    f"{bono.series.date[-1]:%Y-%m-%d}"
)

# 5. Ejecutar los métodos de BondSeries.
print(
    f"\nÚltima rentabilidad: "
    f"{bono.series.current_yield():.3f} %"
)

print(
    f"Rentabilidad máxima del intervalo: "
    f"{bono.series.yield_max():.3f} %"
)

print(
    f"Rentabilidad mínima del intervalo: "
    f"{bono.series.yield_min():.3f} %"
)

print(
    "\nÚltimos cambios entre observaciones "
    "en puntos básicos:"
)

print(bono.series.yield_change_bps().tail())