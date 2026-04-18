#!/bin/bash
curl -v -X POST http://127.0.0.1:11434/api/generate -d '{
  "model": "llama3.1",
  "prompt": "Say hi",
  "stream": false,
  "options": {
    "num_ctx": 4096
  }
}'
