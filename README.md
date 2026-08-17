# IQ Signal Bridge

Read-only FastAPI relay for the IQ Signal AI M1 app. It exposes login, account,
candles, available-assets and logout endpoints only. It contains no trade/order
endpoints and does not call any IQ Option buy/sell methods.

## Render

Deploy using the Docker runtime. Set `BRIDGE_API_KEY` as a secret environment
variable. Use the same value in Base44 as `IQ_BRIDGE_API_KEY`.
