import asyncio
import websockets

async def test_ws():
    uri = "wss://sanabackend.onrender.com/api/ws/beRY39tVRTXni901RTNlJK06o2o2"
    async with websockets.connect(uri) as websocket:
        print("✅ Connected to WebSocket")
        await websocket.send("ping")  # send a test message
        while True:
            msg = await websocket.recv()
            print("📩 Received:", msg)

asyncio.run(test_ws())
