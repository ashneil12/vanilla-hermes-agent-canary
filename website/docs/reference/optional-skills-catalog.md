---
sidebar_position: 9
title: "Optional Skills Catalog"
description: "Official optional skills shipped with hermes-agent — install via hermes skills install official/<category>/<skill>"
---

# Optional Skills Catalog

Optional skills ship with hermes-agent under `optional-skills/` but are **not active by default**. Install them explicitly:

```bash
hermes skills install official/<category>/<skill>
```

For example:

```bash
hermes skills install official/blockchain/solana
hermes skills install official/mlops/flash-attention
```

Each skill below links to a dedicated page with its full definition, setup, and usage.

To uninstall:

```bash
hermes skills uninstall <skill-name>
```

## autonomous-ai-agents

| Skill | Description |
|-------|-------------|
| [**agent-merge-conflict-arbiter**](../user-guide/skills/optional/autonomous-ai-agents/autonomous-ai-agents-agent-merge-conflict-arbiter.md) | Neutral arbiter for merge conflicts between two agents. |
| [**antigravity-cli**](../user-guide/skills/optional/autonomous-ai-agents/autonomous-ai-agents-antigravity-cli.md) | Operate the Antigravity CLI (agy): plugins, auth, sandbox. |
| [**blackbox**](../user-guide/skills/optional/autonomous-ai-agents/autonomous-ai-agents-blackbox.md) | Delegate coding tasks to the Blackbox AI multi-model CLI. |
| [**dynamic-workflow**](../user-guide/skills/optional/autonomous-ai-agents/autonomous-ai-agents-dynamic-workflow.md) | Plan-in-code fan-outs, adversarial verification, waves. |
| [**grok**](../user-guide/skills/optional/autonomous-ai-agents/autonomous-ai-agents-grok.md) | Delegate coding to xAI Grok Build CLI (features, PRs). |
| [**honcho**](../user-guide/skills/optional/autonomous-ai-agents/autonomous-ai-agents-honcho.md) | Configure and troubleshoot Honcho memory for Hermes. |
| [**openhands**](../user-guide/skills/optional/autonomous-ai-agents/autonomous-ai-agents-openhands.md) | Delegate coding to OpenHands CLI (model-agnostic, LiteLLM). |

## bankr

| Skill | Description |
|-------|-------------|
| [**0xwork**](../user-guide/skills/optional/bankr/bankr-0xwork.md) | Find and complete paid tasks on the 0xWork decentralized marketplace (Base chain, USDC escrow). Use when: the agent wants to earn money/USDC by doing work, discover available tasks, claim a bounty, submit deliverables, post tasks with bo... |
| [**agenticbets**](../user-guide/skills/optional/bankr/bankr-agenticbets.md) | Place prediction bets on token prices on Base via AgenticBets. Use when the user wants to bet UP or DOWN on whether a token price will go up or down, check prediction market odds, view open betting rounds, or claim winnings from settled... |
| [**alchemy**](../user-guide/skills/optional/bankr/bankr-alchemy.md) | Blockchain API access via Alchemy. Use when an agent needs to query blockchain data (balances, token prices, NFT ownership, transfer history, transaction simulation, gas estimates) across Ethereum, Base, Arbitrum, BNB, Polygon, Solana, a... |
| [**bankr**](../user-guide/skills/optional/bankr/bankr-bankr.md) | AI-powered crypto trading agent, wallet API, and LLM gateway via natural language. Use when the user wants to trade crypto, check portfolio balances (with PnL and NFTs), view token prices, search tokens, transfer crypto, manage NFTs, use... |
| [**token-scam-analysis**](../user-guide/skills/optional/bankr/bankr-bankr-token-scam-analysis.md) | Deep on-chain scam / rug / soft-rug analysis for EVM tokens (especially Clanker, Doppler, Bankr-style single-admin ERC-20s). Use when the user asks to "analyze this token for scam", "is this a rug", "should I trust this migration", "do a... |
| [**twitter-agent**](../user-guide/skills/optional/bankr/bankr-bankr-twitter-agent.md) | Build and run a Twitter/X agent with a distinct personality and automated workflows |
| [**base**](../user-guide/skills/optional/bankr/bankr-base.md) | Placeholder for Base skill. |
| [**botchan**](../user-guide/skills/optional/bankr/bankr-botchan.md) | CLI for the onchain agent messaging layer on the Base blockchain, built on Net Protocol. Explore other agents, post to feeds, send direct messages, and store information permanently onchain. |
| [**cattown**](../user-guide/skills/optional/bankr/bankr-cattown.md) | Interact with Cat Town — a Farcaster-native game world on Base. Covers KIBBLE staking (stake, claim, unlock, unstake, leaderboard, deposit history); live world state (season, weather, time of day, weekend flag); fishing drops filtered by... |
| [**clanker**](../user-guide/skills/optional/bankr/bankr-clanker.md) | Deploy ERC20 tokens on Base, Ethereum, Arbitrum, and other EVM chains using the Clanker SDK. Use when the user wants to deploy a new token, create a memecoin, set up token vesting, configure airdrops, manage token rewards, claim LP fees,... |
| [**endaoment**](../user-guide/skills/optional/bankr/bankr-endaoment.md) | Donate to charities onchain via Endaoment. Use when the user wants to donate crypto to charity, make a charitable contribution, give to nonprofits, support a cause, or donate to a 501(c)(3). Supports Base, Ethereum, and Optimism. Handles... |
| [**ens-primary-name**](../user-guide/skills/optional/bankr/bankr-ens-primary-name.md) | Set your primary ENS name on Base and other L2s. Use when user wants to set their ENS name, configure reverse resolution, set primary name, or make their address resolve to an ENS name. Supports Base, Arbitrum, Optimism, and Ethereum mai... |
| [**erc-8004**](../user-guide/skills/optional/bankr/bankr-erc-8004.md) | Register AI agents on Ethereum mainnet using ERC-8004 (Trustless Agents). Use when the user wants to register their agent identity on-chain, create an agent profile, claim an agent NFT, set up agent reputation, or make their agent discov... |
| [**gitlawb**](../user-guide/skills/optional/bankr/bankr-gitlawb.md) | Decentralized git for AI agents and humans. Use when the user wants to create repositories, push code, open pull requests, review and merge PRs, manage issues, create or claim bounties, delegate tasks to other agents, register human-read... |
| [**helixa**](../user-guide/skills/optional/bankr/bankr-helixa.md) | Helixa — Onchain identity, reputation, and Cred Scores for AI agents on Base. Use when an agent wants to mint an identity NFT, check its Cred Score, verify social accounts, update traits/narrative, query agent reputation data, check stak... |
| [**hydrex**](../user-guide/skills/optional/bankr/bankr-hydrex.md) | Interact with Hydrex liquidity pools on Base. Use when the user wants to lock HYDX for voting power, check voting power for gauge voting, vote on liquidity pool strategies, view pool information, check voting weights, participate in Hydr... |
| [**litcoin-miner**](../user-guide/skills/optional/bankr/bankr-litcoin.md) | Mine LITCOIN — a proof-of-comprehension and proof-of-research cryptocurrency on Base. Use when the user wants to mine crypto with AI, earn tokens through reading comprehension or solving optimization problems, stake LITCOIN, open vaults,... |
| [**moltycash**](../user-guide/skills/optional/bankr/bankr-moltycash.md) | USDC payments from AI agents to humans via molty.cash. Use when the agent wants to tip someone, hire a person for a task, or create a pay-per-task gig. Payments settle on-chain via x402 on Base using Bankr wallet for signing. Do NOT use... |
| [**neynar**](../user-guide/skills/optional/bankr/bankr-neynar.md) | Interact with Farcaster via Neynar API. Use when the user wants to read Farcaster feeds, look up users, post casts, search content, or interact with the Farcaster social protocol. Requires NEYNAR_API_KEY. |
| [**nookplot**](../user-guide/skills/optional/bankr/bankr-nookplot.md) | Decentralized coordination network for AI agents on Base (Ethereum L2). Use when an agent needs to register an on-chain identity, publish content, message other agents, hire a specialist via the marketplace, post or claim bounties, build... |
| [**onchainkit**](../user-guide/skills/optional/bankr/bankr-onchainkit.md) | Build onchain applications with React components and TypeScript utilities from Coinbase's OnchainKit. Use when users want to create crypto wallets, swap tokens, mint NFTs, build payments, display blockchain identities, or develop any onc... |
| [**productclank-campaigns**](../user-guide/skills/optional/bankr/bankr-productclank.md) | Community-powered growth for builders. Boost amplifies your social posts with authentic community engagement (replies, likes, reposts). Discover finds relevant conversations and generates AI-powered replies at scale. Use Boost when the u... |
| [**qrcoin**](../user-guide/skills/optional/bankr/bankr-qrcoin.md) | Interact with QR Coin auctions on Base. Use when the user wants to participate in qrcoin.fun QR code auctions — check auction status, view current bids, create new bids, or contribute to existing bids. QR Coin lets you bid to display URL... |
| [**quicknode**](../user-guide/skills/optional/bankr/bankr-quicknode.md) | Blockchain RPC and data access via Quicknode. Use when an agent needs to read onchain data (balances, token prices, transaction status, gas estimates, block data) across Base, Ethereum, Polygon, Solana, or Unichain. Supports both API key... |
| [**quotient-api**](../user-guide/skills/optional/bankr/bankr-quotient.md) | Accesses Quotient market intelligence through either x402 micropayments or API key auth, with explicit 402 challenge/settle handling when using x402. |
| [**signals**](../user-guide/skills/optional/bankr/bankr-signals.md) | Transaction-verified trading signals on Base. Register agent as signal provider, publish trades with TX hash proof, consume signals from top performers via REST API. All track records verified against blockchain data. No fake performance... |
| [**siwa**](../user-guide/skills/optional/bankr/bankr-siwa.md) | SIWA (Sign-In With Agent) authentication for ERC-8004 registered agents. |
| [**stakr-protocol**](../user-guide/skills/optional/bankr/bankr-stakr.md) | Interact with the Stakr protocol — ERC-4626 vaults with multi-reward staking. Use when the user or an agent needs to work with Stakr vaults, add or modify rewards (addRewardToken, addRewards, modifyRewardToken, modifyReward), create or m... |
| [**symbiosis**](../user-guide/skills/optional/bankr/bankr-symbiosis.md) | Cross-chain token swaps across 54+ blockchains via Symbiosis protocol. Use when the user wants to swap or bridge tokens between any chains — Base, Ethereum, Polygon, Arbitrum, Optimism, BNB Chain, Avalanche, Solana, Bitcoin, TON, Tron, a... |
| [**trails**](../user-guide/skills/optional/bankr/bankr-trails.md) | Trails — Cross-chain swap, bridge, and DeFi orchestration via Sequence. Use when an agent wants to swap tokens across chains, bridge assets, fund a Bankr wallet from any chain, deposit into yield vaults (Aave, Morpho), get token prices,... |
| [**trustlayer-sybil-scanner**](../user-guide/skills/optional/bankr/bankr-trustlayer-sybil-scanner.md) | Feedback forensics for ERC-8004 agents. Detects Sybil rings, fake reviews, rating manipulation, and reputation laundering across 20 chains. No API key needed. |
| [**veil**](../user-guide/skills/optional/bankr/bankr-veil.md) | Privacy and shielded transactions on Base via Veil Cash (veil.cash). Deposit ETH or USDC into private pools, withdraw/transfer privately using ZK proofs. Manage Veil keypairs, check private/queue balances across all pools, and submit dep... |
| [**yoink**](../user-guide/skills/optional/bankr/bankr-yoink.md) | Play Yoink, an onchain capture-the-flag game on Base. Yoink the flag from the current holder, check game stats and leaderboards, view player scores, and compete for the trophy. Uses Bankr for transaction execution. |
| [**zapper**](../user-guide/skills/optional/bankr/bankr-zapper.md) | Placeholder for Zapper skill. |
| [**zerion**](../user-guide/skills/optional/bankr/bankr-zerion.md) | Interpreted crypto wallet data for AI agents. Use when an agent needs portfolio values, token positions, DeFi positions, NFT holdings, transaction history, PnL data, token prices, charts, gas prices, swap quotes, or DApp information acro... |
| [**zyfai**](../user-guide/skills/optional/bankr/bankr-zyfai.md) | Earn yield on any Ethereum wallet on Base, Arbitrum, and Plasma. Use when a user wants passive DeFi yield on their funds. Deploys a non-custodial deterministic subaccount (Safe) linked to their EOA, enables automated yield optimization,... |

## blockchain

| Skill | Description |
|-------|-------------|
| [**evm**](../user-guide/skills/optional/blockchain/blockchain-evm.md) | Read-only EVM client: wallets, tokens, gas across 8 chains. |
| [**hyperliquid**](../user-guide/skills/optional/blockchain/blockchain-hyperliquid.md) | Hyperliquid market data, account history, trade review. |
| [**solana**](../user-guide/skills/optional/blockchain/blockchain-solana.md) | Query Solana wallets, tokens, txs, and NFTs in USD. |

## communication

| Skill | Description |
|-------|-------------|
| [**one-three-one-rule**](../user-guide/skills/optional/communication/communication-one-three-one-rule.md) | 1-3-1 decision briefs: problem, three options, one pick. |

## creative

| Skill | Description |
|-------|-------------|
| [**ai-presenter-video**](../user-guide/skills/optional/creative/creative-ai-presenter-video.md) | Make a verified AI presenter video from script + image. |
| [**archify**](../user-guide/skills/optional/creative/creative-archify.md) | Validated interactive HTML diagrams, upstream-maintained. |
| [**ascii-art**](../user-guide/skills/optional/creative/creative-ascii-art.md) | ASCII art: pyfiglet, cowsay, boxes, image-to-ascii. |
| [**audiocraft-audio-generation**](../user-guide/skills/optional/creative/creative-audiocraft-audio-generation.md) | AudioCraft: MusicGen text-to-music, AudioGen text-to-sound. |
| [**auteur**](../user-guide/skills/optional/creative/creative-auteur.md) | Design and build cinematic, award-level web pages. |
| [**baoyu-article-illustrator**](../user-guide/skills/optional/creative/creative-baoyu-article-illustrator.md) | Article illustrations: type × style × palette consistency. |
| [**baoyu-comic**](../user-guide/skills/optional/creative/creative-baoyu-comic.md) | Knowledge comics (知识漫画): educational, biography, tutorial. |
| [**comfyui**](../user-guide/skills/optional/creative/creative-comfyui.md) | Generate images, video, and audio via diffusion workflows. |
| [**concept-diagrams**](../user-guide/skills/optional/creative/creative-concept-diagrams.md) | Generate flat, minimal educational SVG visuals as HTML. |
| [**creative-ideation**](../user-guide/skills/optional/creative/creative-creative-ideation.md) | Generate ideas via named methods from creative practice. |
| [**draw-your-font**](../user-guide/skills/optional/creative/creative-draw-your-font.md) | Turn a handwriting photo into an installable TTF font. |
| [**dream-loop**](../user-guide/skills/optional/creative/creative-dream-loop.md) | Build stunning 3D scenes via a concept-art fidelity loop. |
| [**excalidraw**](../user-guide/skills/optional/creative/creative-excalidraw.md) | Hand-drawn Excalidraw JSON diagrams (arch, flow, seq). |
| [**heartmula**](../user-guide/skills/optional/creative/creative-heartmula.md) | HeartMuLa: Suno-like song generation from lyrics + tags. |
| [**hyperframes**](../user-guide/skills/optional/creative/creative-hyperframes.md) | Render MP4/WebM videos from HTML compositions. |
| [**impeccable**](../user-guide/skills/optional/creative/creative-impeccable.md) | Frontend design guidance, upstream-maintained (impeccable). |
| [**ip-as-logo**](../user-guide/skills/optional/creative/creative-ip-as-logo.md) | Design minimal cute IP mascot marks readable at 32px. |
| [**kanban-video-orchestrator**](../user-guide/skills/optional/creative/creative-kanban-video-orchestrator.md) | Plan and run multi-agent video production pipelines. |
| [**meme-generation**](../user-guide/skills/optional/creative/creative-meme-generation.md) | Create meme PNGs from templates with Pillow text overlay. |
| [**mono-color**](../user-guide/skills/optional/creative/creative-mono-color.md) | Generate one- or two-ink editorial print poster images. |
| [**pixel-art**](../user-guide/skills/optional/creative/creative-pixel-art.md) | Pixel art w/ era palettes (NES, Game Boy, PICO-8). |
| [**pretext**](../user-guide/skills/optional/creative/creative-pretext.md) | Build creative browser demos with DOM-free text layout. |
| [**simple-english**](../user-guide/skills/optional/creative/creative-simple-english.md) | Rewrite text to ASD-STE100 Simplified Technical English. |
| [**sketch**](../user-guide/skills/optional/creative/creative-sketch.md) | Throwaway HTML mockups: 2-3 design variants to compare. |
| [**social-media-content-calendar**](../user-guide/skills/optional/creative/creative-social-media-content-calendar.md) | Plan multi-platform social campaigns: briefs to posting. |
| [**system-atlas**](../user-guide/skills/optional/creative/creative-system-atlas.md) | Build explorable isometric architecture atlases as HTML. |
| [**tldraw-offline**](../user-guide/skills/optional/creative/creative-tldraw-offline.md) | Drive and script tldraw offline canvases with an agent. |
| [**unreal-mcp**](../user-guide/skills/optional/creative/creative-unreal-mcp.md) | Automate Unreal Engine editor scenes, actors, and renders. |

## data-science

| Skill | Description |
|-------|-------------|
| [**jupyter-notebook**](../user-guide/skills/optional/data-science/data-science-jupyter-notebook.md) | Iterative Python via live Jupyter kernel (hamelnb). |

## devops

| Skill | Description |
|-------|-------------|
| [**actual-setup**](../user-guide/skills/optional/devops/devops-actual-setup.md) | Set up Actual Computer (actual.inc) inference in Hermes. |
| [**docker-management**](../user-guide/skills/optional/devops/devops-docker-management.md) | Manage Docker containers, images, volumes, and Compose. |
| [**hermes-s6-container-supervision**](../user-guide/skills/optional/devops/devops-hermes-s6-container-supervision.md) | Modify or debug s6 services in the Hermes Docker image. |
| [**inference-sh-cli**](../user-guide/skills/optional/devops/devops-inference-sh-cli.md) | Run 150+ AI apps (image, video, LLM) via inference.sh CLI. |
| [**pinggy-tunnel**](../user-guide/skills/optional/devops/devops-pinggy-tunnel.md) | Zero-install localhost tunnels over SSH via Pinggy. |
| [**setup-wizard-generator**](../user-guide/skills/optional/devops/devops-setup-wizard-generator.md) | Generate a bash wizard guiding a human through manual setup. |
| [**watchers**](../user-guide/skills/optional/devops/devops-watchers.md) | Poll RSS, JSON APIs, and GitHub with watermark dedup. |

## dogfood

| Skill | Description |
|-------|-------------|
| [**adversarial-ux-test**](../user-guide/skills/optional/dogfood/dogfood-adversarial-ux-test.md) | Roleplay a hostile user to find and triage UX pain points. |

## email

| Skill | Description |
|-------|-------------|
| [**agentmail**](../user-guide/skills/optional/email/email-agentmail.md) | Use when an agent needs AgentMail CLI email inboxes. |

## finance

| Skill | Description |
|-------|-------------|
| [**3-statement-model**](../user-guide/skills/optional/finance/finance-3-statement-model.md) | Build integrated IS/BS/CF financial workbooks in Excel. |
| [**comps-analysis**](../user-guide/skills/optional/finance/finance-comps-analysis.md) | Build comparable-company valuation workbooks in Excel. |
| [**dcf-model**](../user-guide/skills/optional/finance/finance-dcf-model.md) | Build discounted cash flow valuation workbooks in Excel. |
| [**excel-author**](../user-guide/skills/optional/finance/finance-excel-author.md) | Build auditable financial workbooks headless via openpyxl. |
| [**lbo-model**](../user-guide/skills/optional/finance/finance-lbo-model.md) | Build leveraged buyout workbooks with IRR/MOIC in Excel. |
| [**merger-model**](../user-guide/skills/optional/finance/finance-merger-model.md) | Build M&A accretion/dilution workbooks in Excel. |
| [**polymarket**](../user-guide/skills/optional/finance/finance-polymarket.md) | Query Polymarket: markets, prices, orderbooks, history. |
| [**pptx-author**](../user-guide/skills/optional/finance/finance-pptx-author.md) | Build PowerPoint decks headless with python-pptx. |
| [**stocks**](../user-guide/skills/optional/finance/finance-stocks.md) | Stock quotes, history, search, compare, crypto via Yahoo. |

## gaming

| Skill | Description |
|-------|-------------|
| [**minecraft-modpack-server**](../user-guide/skills/optional/gaming/gaming-minecraft-modpack-server.md) | Host modded Minecraft servers (CurseForge, Modrinth). |
| [**pokemon-player**](../user-guide/skills/optional/gaming/gaming-pokemon-player.md) | Play Pokemon via headless emulator + RAM reads. |

## health

| Skill | Description |
|-------|-------------|
| [**fitness-nutrition**](../user-guide/skills/optional/health/health-fitness-nutrition.md) | Workout planning, macros, and body metrics via wger/USDA. |
| [**neuroskill-bci**](../user-guide/skills/optional/health/health-neuroskill-bci.md) | Use live BCI cognitive and mood state from NeuroSkill. |

## mcp

| Skill | Description |
|-------|-------------|
| [**fastmcp**](../user-guide/skills/optional/mcp/mcp-fastmcp.md) | Build, test, and deploy Python MCP servers. |
| [**mcp-oauth-remote-gateway**](../user-guide/skills/optional/mcp/mcp-mcp-oauth-remote-gateway.md) | Manual OAuth for remote MCP servers on headless gateways. |
| [**mcporter**](../user-guide/skills/optional/mcp/mcp-mcporter.md) | List, auth, and call MCP servers/tools from the terminal. |

## migration

| Skill | Description |
|-------|-------------|
| [**openclaw-migration**](../user-guide/skills/optional/migration/migration-openclaw-migration.md) | Import an OpenClaw setup (memories, skills) into Hermes. |

## mlops

| Skill | Description |
|-------|-------------|
| [**accelerate**](../user-guide/skills/optional/mlops/mlops-accelerate.md) | Run PyTorch training across GPUs with minimal changes. |
| [**axolotl**](../user-guide/skills/optional/mlops/mlops-training-axolotl.md) | Axolotl: YAML LLM fine-tuning (LoRA, DPO, GRPO). |
| [**chroma**](../user-guide/skills/optional/mlops/mlops-chroma.md) | Embedding database for RAG and semantic search. |
| [**clip**](../user-guide/skills/optional/mlops/mlops-clip.md) | Zero-shot image classification and image-text search. |
| [**dspy**](../user-guide/skills/optional/mlops/mlops-research-dspy.md) | DSPy: declarative LM programs, auto-optimize prompts, RAG. |
| [**evaluating-llms-harness**](../user-guide/skills/optional/mlops/mlops-evaluation-evaluating-llms-harness.md) | lm-eval-harness: benchmark LLMs (MMLU, GSM8K, etc.). |
| [**faiss**](../user-guide/skills/optional/mlops/mlops-faiss.md) | Fast vector similarity search at billion scale. |
| [**flash-attention**](../user-guide/skills/optional/mlops/mlops-flash-attention.md) | Speed up long-sequence transformer training and inference. |
| [**guidance**](../user-guide/skills/optional/mlops/mlops-guidance.md) | Constrain LLM output with grammars; guarantee valid JSON. |
| [**huggingface-hub**](../user-guide/skills/optional/mlops/mlops-models-huggingface-hub.md) | HuggingFace hf CLI: search/download/upload models, datasets. |
| [**huggingface-tokenizers**](../user-guide/skills/optional/mlops/mlops-huggingface-tokenizers.md) | Fast BPE/WordPiece tokenization and custom vocab training. |
| [**instructor**](../user-guide/skills/optional/mlops/mlops-instructor.md) | Structured LLM outputs validated with Pydantic. |
| [**lambda-labs**](../user-guide/skills/optional/mlops/mlops-lambda-labs.md) | On-demand GPU cloud instances for ML training. |
| [**llama-cpp**](../user-guide/skills/optional/mlops/mlops-inference-llama-cpp.md) | llama.cpp local GGUF inference + HF Hub model discovery. |
| [**llava**](../user-guide/skills/optional/mlops/mlops-llava.md) | Vision-language chat: VQA, captioning, image dialogue. |
| [**modal**](../user-guide/skills/optional/mlops/mlops-modal.md) | Serverless GPU cloud for ML jobs and model APIs. |
| [**nemo-curator**](../user-guide/skills/optional/mlops/mlops-nemo-curator.md) | Curate LLM training data: dedupe, filter, PII redaction. |
| [**obliteratus**](../user-guide/skills/optional/mlops/mlops-obliteratus.md) | OBLITERATUS: abliterate LLM refusals (diff-in-means). |
| [**outlines**](../user-guide/skills/optional/mlops/mlops-inference-outlines.md) | Outlines: structured JSON/regex/Pydantic LLM generation. |
| [**peft**](../user-guide/skills/optional/mlops/mlops-peft.md) | Fine-tune large LLMs with LoRA on limited GPU memory. |
| [**pinecone**](../user-guide/skills/optional/mlops/mlops-pinecone.md) | Managed vector DB for production RAG and search. |
| [**pytorch-fsdp**](../user-guide/skills/optional/mlops/mlops-pytorch-fsdp.md) | Fully sharded data-parallel training for large models. |
| [**pytorch-lightning**](../user-guide/skills/optional/mlops/mlops-pytorch-lightning.md) | Clean training loops with built-in distributed support. |
| [**qdrant**](../user-guide/skills/optional/mlops/mlops-qdrant.md) | Vector search engine for production RAG systems. |
| [**saelens**](../user-guide/skills/optional/mlops/mlops-saelens.md) | Train sparse autoencoders to interpret model features. |
| [**segment-anything-model**](../user-guide/skills/optional/mlops/mlops-models-segment-anything-model.md) | SAM: zero-shot image segmentation via points, boxes, masks. |
| [**serving-llms-vllm**](../user-guide/skills/optional/mlops/mlops-inference-serving-llms-vllm.md) | vLLM: high-throughput LLM serving, OpenAI API, quantization. |
| [**simpo**](../user-guide/skills/optional/mlops/mlops-simpo.md) | Reference-free preference alignment, simpler than DPO. |
| [**slime**](../user-guide/skills/optional/mlops/mlops-slime.md) | RL post-training for LLMs with Megatron and SGLang. |
| [**stable-diffusion**](../user-guide/skills/optional/mlops/mlops-stable-diffusion.md) | Text-to-image generation, inpainting, and img2img. |
| [**tensorrt-llm**](../user-guide/skills/optional/mlops/mlops-tensorrt-llm.md) | High-throughput LLM inference on NVIDIA GPUs. |
| [**torchtitan**](../user-guide/skills/optional/mlops/mlops-torchtitan.md) | Pretrain LLMs at scale with PyTorch 4D parallelism. |
| [**trl-fine-tuning**](../user-guide/skills/optional/mlops/mlops-training-trl-fine-tuning.md) | TRL: SFT, DPO, GRPO, RLOO reward modeling for LLM RLHF. |
| [**unsloth**](../user-guide/skills/optional/mlops/mlops-training-unsloth.md) | Unsloth: 2-5x faster LoRA/QLoRA fine-tuning, less VRAM. |
| [**weights-and-biases**](../user-guide/skills/optional/mlops/mlops-evaluation-weights-and-biases.md) | W&B: log ML experiments, sweeps, model registry, dashboards. |
| [**whisper**](../user-guide/skills/optional/mlops/mlops-whisper.md) | Transcribe and translate speech in 99 languages. |

## payments

| Skill | Description |
|-------|-------------|
| [**mpp-agent**](../user-guide/skills/optional/payments/payments-mpp-agent.md) | Pay HTTP 402 APIs via Machine Payments Protocol (MPP). |
| [**stripe-link-cli**](../user-guide/skills/optional/payments/payments-stripe-link-cli.md) | Agent payments via Stripe Link — cards, SPT, approvals. |
| [**stripe-projects**](../user-guide/skills/optional/payments/payments-stripe-projects.md) | Provision SaaS services + sync creds via Stripe Projects. |

## productivity

| Skill | Description |
|-------|-------------|
| [**canvas**](../user-guide/skills/optional/productivity/productivity-canvas.md) | Fetch Canvas LMS courses and assignments via API token. |
| [**decision-questionnaire**](../user-guide/skills/optional/productivity/productivity-decision-questionnaire.md) | Turn an unanswerable decision into a questionnaire doc. |
| [**here-now**](../user-guide/skills/optional/productivity/productivity-here-now.md) | Publish sites to &#123;slug&#125;.here.now and store files in Drives. |
| [**live-dashboard**](../user-guide/skills/optional/productivity/productivity-live-dashboard.md) | Build self-updating dashboards from live sources. |
| [**memento-flashcards**](../user-guide/skills/optional/productivity/productivity-memento-flashcards.md) | Spaced-repetition flashcards: create, review, quiz, export. |
| [**property-listings**](../user-guide/skills/optional/productivity/productivity-property-listings.md) | Present property and rental listings as desktop cards. |
| [**shop**](../user-guide/skills/optional/productivity/productivity-shop.md) | Shop catalog search, checkout, order tracking, returns. |
| [**shopify**](../user-guide/skills/optional/productivity/productivity-shopify.md) | Query Shopify Admin/Storefront GraphQL APIs via curl. |
| [**siyuan**](../user-guide/skills/optional/productivity/productivity-siyuan.md) | Query and edit a SiYuan knowledge base via its API. |
| [**telephony**](../user-guide/skills/optional/productivity/productivity-telephony.md) | Provision Twilio numbers, SMS/MMS, and AI outbound calls. |

## research

| Skill | Description |
|-------|-------------|
| [**bioinformatics**](../user-guide/skills/optional/research/research-bioinformatics.md) | Gateway to 400+ genomics and computational biology skills. |
| [**blogwatcher**](../user-guide/skills/optional/research/research-blogwatcher.md) | Monitor blogs and RSS/Atom feeds via blogwatcher-cli tool. |
| [**darwinian-evolver**](../user-guide/skills/optional/research/research-darwinian-evolver.md) | Evolve prompts/regex/SQL/code with Imbue's evolution loop. |
| [**domain-intel**](../user-guide/skills/optional/research/research-domain-intel.md) | Passive recon of subdomains, SSL certs, WHOIS, and DNS. |
| [**drug-discovery**](../user-guide/skills/optional/research/research-drug-discovery.md) | Drug discovery: ChEMBL search, drug-likeness, interactions. |
| [**duckduckgo-search**](../user-guide/skills/optional/research/research-duckduckgo-search.md) | Free keyless web, news, and image search via ddgs. |
| [**gitnexus-explorer**](../user-guide/skills/optional/research/research-gitnexus-explorer.md) | Serve an interactive codebase knowledge graph web UI. |
| [**osint-investigation**](../user-guide/skills/optional/research/research-osint-investigation.md) | Follow the money via public records and sanctions data. |
| [**parallel-cli**](../user-guide/skills/optional/research/research-parallel-cli.md) | Agent-native web search, deep research, and enrichment. |
| [**pinecone-research**](../user-guide/skills/optional/research/research-pinecone-research.md) | Agent RAG and long-term memory with Pinecone. |
| [**qmd**](../user-guide/skills/optional/research/research-qmd.md) | Hybrid local search over notes, docs, and transcripts. |
| [**research-paper-writing**](../user-guide/skills/optional/research/research-research-paper-writing.md) | Write ML papers for NeurIPS/ICML/ICLR: design→submit. |
| [**rss-feeds**](../user-guide/skills/optional/research/research-rss-feeds.md) | Read RSS, Atom, JSON feeds; discover feeds behind a page. |
| [**scrapling**](../user-guide/skills/optional/research/research-scrapling.md) | Scrape sites with stealth browsing and Cloudflare bypass. |
| [**searxng-search**](../user-guide/skills/optional/research/research-searxng-search.md) | Free keyless meta-search aggregating 70+ engines. |

## security

| Skill | Description |
|-------|-------------|
| [**1password**](../user-guide/skills/optional/security/security-1password.md) | Set up op CLI, sign in, and read or inject secrets. |
| [**godmode**](../user-guide/skills/optional/security/security-godmode.md) | Jailbreak LLMs: Parseltongue, GODMODE, ULTRAPLINIAN. |
| [**oss-forensics**](../user-guide/skills/optional/security/security-oss-forensics.md) | GitHub supply-chain forensics: recovery, IOCs, reporting. |
| [**sherlock**](../user-guide/skills/optional/security/security-sherlock.md) | Find accounts for a username across 400+ platforms. |
| [**unbroker**](../user-guide/skills/optional/security/security-unbroker.md) | Autonomously remove your info from data-broker sites. |
| [**web-pentest**](../user-guide/skills/optional/security/security-web-pentest.md) | Authorized web pentest: recon, proof-based exploits, report. |

## smart-home

| Skill | Description |
|-------|-------------|
| [**openhue**](../user-guide/skills/optional/smart-home/smart-home-openhue.md) | Control Philips Hue lights, scenes, rooms via OpenHue CLI. |

## social-media

| Skill | Description |
|-------|-------------|
| [**reddit-reading**](../user-guide/skills/optional/social-media/social-media-reddit-reading.md) | Read Reddit: subreddits, search, threads, users. No browser. |

## software-development

| Skill | Description |
|-------|-------------|
| [**ast-grep**](../user-guide/skills/optional/software-development/software-development-ast-grep.md) | AST-aware structural code search and rewrite via ast-grep. |
| [**code-wiki**](../user-guide/skills/optional/software-development/software-development-code-wiki.md) | Generate wiki docs + Mermaid diagrams for any codebase. |
| [**grill-me**](../user-guide/skills/optional/software-development/software-development-grill-me.md) | Adversarial plan interview before implementation. |
| [**pr-lens**](../user-guide/skills/optional/software-development/software-development-pr-lens.md) | Draw code changes as animated architecture/data-flow SVGs. |
| [**rest-graphql-debug**](../user-guide/skills/optional/software-development/software-development-rest-graphql-debug.md) | Debug REST/GraphQL APIs: status codes, auth, schemas, repro. |
| [**subagent-driven-development**](../user-guide/skills/optional/software-development/software-development-subagent-driven-development.md) | Execute plans via delegate_task subagents (2-stage review). |

## web-development

| Skill | Description |
|-------|-------------|
| [**cloudflare-temporary-deploy**](../user-guide/skills/optional/web-development/web-development-cloudflare-temporary-deploy.md) | Deploy a Worker live, no account, via wrangler --temporary. |
| [**har-derived-api-client**](../user-guide/skills/optional/web-development/web-development-har-derived-api-client.md) | Record a site's XHR into a HAR, derive an HTTP client. |
| [**page-agent**](../user-guide/skills/optional/web-development/web-development-page-agent.md) | Embed an in-page natural-language GUI copilot in web apps. |
| [**publish-site**](../user-guide/skills/optional/web-development/web-development-publish-site.md) | Versioned site deploys to GitHub/Cloudflare/Netlify Pages. |
| [**scrollcraft**](../user-guide/skills/optional/web-development/web-development-scrollcraft.md) | Premium scroll-driven landing pages; scroll = timeline. |

## yuanbao

| Skill | Description |
|-------|-------------|
| [**yuanbao**](../user-guide/skills/optional/yuanbao/yuanbao-yuanbao.md) | Yuanbao (元宝) groups: @mention users, query info/members. |

---

## Contributing Optional Skills

To add a new optional skill to the repository:

1. Create a directory under `optional-skills/<category>/<skill-name>/`
2. Add a `SKILL.md` with standard frontmatter (name, description, version, author)
3. Include any supporting files in `references/`, `templates/`, or `scripts/` subdirectories
4. Submit a pull request — the skill will appear in this catalog and get its own docs page once merged
