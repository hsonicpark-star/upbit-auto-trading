import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { SSEClientTransport } from '@modelcontextprotocol/sdk/client/sse.js';

// Smithery CLI 설정 파일에서 가져온 값
const MCP_SERVER_URL = "https://server.smithery.ai/KISOpenAPI/kis-code-assistant-mcp";
const API_KEY = "smry_EsUBClsKJDY4NTMxY2NhLWYyZTItNGQzMC04ZDIwLTU5ZDNkOGE5MDI0OBgDIgkKBwgKEgMYgAgyJgokCgIIGxIGCAUSAggFGhYKBAoCCAUKCAoGILT4idEGCgQaAggCEiQIABIg5-YKiM52jhK9vWfgKiAnqSQ2wHyhOGE8imjM2O2nJJsaQLqA3wtwx3pcsGDLr49Mgnxlv8hkw25WaSlGddKEZ0r3hnMrJWQONd4HK971LTASSYTHzZSxM4Jjt_qNF--7bA0amQEKLwoBdBgDMigKJgoCCBsSBwgFEgMIgQgaFwoFCgMIgQgKCAoGILT4idEGCgQaAggCEiQIABIg-5U01sj6x0NO9CTLwdiUozF_pKC4DRt8RoOpb2FrHJEaQJOHTVyzrpLR6ivBmOabfgDVfeEFg3C3_cg_PdM55kajW3-BbcIXlkGLtFGKpFyjwru6YeO4783FU4Kgiw8bKgkiIgogM8VroXq6mNUjuCVhQmVb133_j4NvgNDJXsGEF88lZdg=";

async function run() {
  console.log("Starting MCP Client...");
  
  // Smithery는 SSE(Server-Sent Events) 방식을 사용하여 원격 연결 제공
  const transport = new SSEClientTransport(new URL(`${MCP_SERVER_URL}/messages`), {
    headers: {
      "Authorization": `Bearer ${API_KEY}`,
      "Accept": "application/json"
    }
  });

  const client = new Client(
    {
      name: "mcp-test-client",
      version: "1.0.0",
    },
    {
      capabilities: {},
    }
  );

  try {
    await client.connect(transport);
    console.log("Connected to MCP Server!");
    
    // 도구 목록 조회
    const toolsResult = await client.listTools();
    console.log("Available Tools:");
    console.log(JSON.stringify(toolsResult, null, 2));
    
  } catch (error) {
    console.error("Failed to connect or list tools:", error);
  } finally {
    try {
      await client.close();
    } catch (e) {}
  }
}

run().catch(console.error);
