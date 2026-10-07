---
title: "Siwa — SIWA (Sign-In With Agent) authentication for ERC-8004 registered agents"
sidebar_label: "Siwa"
description: "SIWA (Sign-In With Agent) authentication for ERC-8004 registered agents"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# Siwa

SIWA (Sign-In With Agent) authentication for ERC-8004 registered agents.

## Skill metadata

| | |
|---|---|
| Source | Optional — install with `hermes skills install official/bankr/siwa` |
| Path | `optional-skills/bankr/siwa` |
| Version | `0.2.0` |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Hermes loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# SIWA SDK

Sign-In With Agent (SIWA) lets AI agents authenticate with services using their ERC-8004 onchain identity.

## Install

```bash
npm install @buildersgarden/siwa
```

## Skills

### Agent-Side (Signing)

Choose based on your wallet provider:

- [Bankr](https://github.com/NousResearch/hermes-agent/blob/main/optional-skills/bankr/siwa/references/bankr-signer.md) — Bankr Agent API wallets

### Server-Side (Verification)

- [Server-Side Verification](https://github.com/NousResearch/hermes-agent/blob/main/optional-skills/bankr/siwa/references/server-side.md) — Next.js, Express, Hono, Fastify

## SDK Modules

| Import | Description |
|--------|-------------|
| `@buildersgarden/siwa` | Core: signSIWAMessage, verifySIWA, createSIWANonce |
| `@buildersgarden/siwa/signer` | Signer factories |
| `@buildersgarden/siwa/erc8128` | ERC-8128 HTTP signing/verification |
| `@buildersgarden/siwa/receipt` | HMAC receipt helpers |
| `@buildersgarden/siwa/nonce-store` | Nonce stores (Memory, Redis, KV) |
| `@buildersgarden/siwa/next` | Next.js middleware |
| `@buildersgarden/siwa/express` | Express middleware |
| `@buildersgarden/siwa/hono` | Hono middleware |
| `@buildersgarden/siwa/fastify` | Fastify middleware |

## Links

- [Latest version of this skill](https://siwa.id/skill.md)
- [Documentation](https://siwa.id/docs)
- [ERC-8004](https://eips.ethereum.org/EIPS/eip-8004)
- [ERC-8128](https://eips.ethereum.org/EIPS/eip-8128)
