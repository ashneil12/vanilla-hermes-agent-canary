// @vitest-environment node
//
// CI drift guard for the hosted-web bridge (`web-shim.ts`).
//
// Why this exists. Upstream grows the Electron preload bridge every release
// (~120 -> ~148 keys across one sync). The web shim cannot implement all of it,
// and it must NOT paper over the gap with a catch-all no-op Proxy: the renderer
// feature-detects Electron-only UI (`window.hermesDesktop?.cloud`,
// `typeof ...openWindow === 'function'`, `if (!desktop.renamePath) throw`), so a
// no-op would switch those surfaces ON and turn "unavailable" errors into silent
// failures. Missing keys therefore stay `undefined` on purpose.
//
// What can actually break is a key declared REQUIRED in global.d.ts (no `?`)
// that the renderer calls without a feature check. So after every upstream sync
// this test makes a human decide, once, for each new required key:
//   - implement it in web-shim.ts, or
//   - add it to ACKNOWLEDGED_ABSENT below (Electron-only, guarded / unreachable).
// and for each new unguarded-looking call site of an acknowledged key, review it
// and add it to REVIEWED_USE_SITES.
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

import ts from 'typescript'
import { describe, expect, it } from 'vitest'

const SRC = join(dirname(fileURLToPath(import.meta.url)), '..')
const APP = join(SRC, '..')

/** Keys only the web shim defines (no Electron preload twin). */
const SHIM_ONLY_KEYS = ['getAdminPanelUrl', 'openAdminPanel']

/**
 * Required bridge keys the web shim deliberately does not implement. Each is
 * Electron-only UI the renderer guards (`desktop?.cloud`, `typeof fn ===
 * 'function'`, `can*()` helpers) or only reaches from oauth-mode / native flows
 * that the token-mode shim never enters. Keep sorted.
 */
const ACKNOWLEDGED_ABSENT = [
  'claimAmbientCue',
  'cloud',
  'connections',
  'continueBootstrapLocal',
  'findInPage',
  'getGatewayWsUrl', // optional in @hermes/shared deps; token mode falls back to conn.wsUrl
  'getPoolLimits',
  'getProfileRoutes',
  'getSecretStorageEncryption',
  'oauthLoginConnectionConfig',
  'oauthLogoutConnectionConfig',
  'onBrowserPopoutClosed',
  'onFoundInPage',
  'onOpenFindBarRequested',
  'openBrowserWindow',
  'openSessionInTerminal',
  'openSessionWindow',
  'openWindow',
  'petOverlay',
  'probeConnectionConfig',
  'quickEntry',
  'revalidateConnection',
  'sanitizeWorkspaceCwd',
  'savePastedText',
  'setPoolLimits',
  'setSecretStorageEncryption',
  'sshConfigHosts',
  'sshResolveHost',
  'stopFindInPage',
  'themes',
  'touchBackend',
  'uninstall',
  'windowControls'
]

/**
 * Acknowledged-absent keys that the renderer calls without its own `?.` somewhere. Reviewed: each
 * call sits behind a guard in the surrounding code (an early `return`, `canOpen*()`,
 * `state.envOverride`, an oauth-only / native-only branch). Keyed by NAME, not file: upstream moves
 * code between files all the time (a `remote-setup/` refactor relocated five of these sites), and a
 * guard that fails on every move gets deleted. A NEW unguarded-looking key still fails.
 */
const REVIEWED_UNGUARDED_KEYS = [
  'cloud',
  'connections',
  'continueBootstrapLocal',
  'oauthLoginConnectionConfig',
  'oauthLogoutConnectionConfig',
  'openBrowserWindow',
  'openSessionInTerminal',
  'openSessionWindow',
  'openWindow',
  'probeConnectionConfig',
  'quickEntry',
  'setSecretStorageEncryption',
  'sshConfigHosts',
  'sshResolveHost'
]

const parse = (file: string) =>
  ts.createSourceFile(
    file,
    readFileSync(file, 'utf8'),
    ts.ScriptTarget.Latest,
    true,
    file.endsWith('x') ? ts.ScriptKind.TSX : ts.ScriptKind.TS
  )

const objectKeys = (node: ts.ObjectLiteralExpression) =>
  node.properties.flatMap(p => (p.name ? [p.name.getText().replace(/^['"]|['"]$/g, '')] : []))

function preloadKeys(): string[] {
  let keys: string[] = []

  const visit = (node: ts.Node) => {
    if (
      ts.isCallExpression(node) &&
      node.expression.getText().endsWith('exposeInMainWorld') &&
      node.arguments[0]?.getText().includes('hermesDesktop') &&
      ts.isObjectLiteralExpression(node.arguments[1])
    ) {
      keys = objectKeys(node.arguments[1])
    }

    ts.forEachChild(node, visit)
  }

  visit(parse(join(APP, 'electron/preload.ts')))

  return keys
}

function declaredKeys(): { optional: string[]; required: string[] } {
  const optional: string[] = []
  const required: string[] = []

  const visit = (node: ts.Node) => {
    if (
      ts.isPropertySignature(node) &&
      node.name.getText() === 'hermesDesktop' &&
      node.type &&
      ts.isTypeLiteralNode(node.type)
    ) {
      for (const member of node.type.members) {
        if (member.name) {
          ;(member.questionToken ? optional : required).push(member.name.getText())
        }
      }
    }

    ts.forEachChild(node, visit)
  }

  visit(parse(join(SRC, 'global.d.ts')))

  return { optional, required }
}

function shimKeys(): string[] {
  let keys: string[] = []

  const visit = (node: ts.Node) => {
    if (
      ts.isVariableDeclaration(node) &&
      node.name.getText() === 'bridge' &&
      node.initializer &&
      ts.isObjectLiteralExpression(node.initializer)
    ) {
      keys = objectKeys(node.initializer)
    }

    ts.forEachChild(node, visit)
  }

  visit(parse(join(SRC, 'lib/web-shim.ts')))

  return keys
}

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)

    if (entry.isDirectory()) {
      if (entry.name !== 'node_modules' && entry.name !== 'test') {
        sourceFiles(path, out)
      }
    } else if (/\.tsx?$/.test(entry.name) && !/\.test\.|\.d\.ts$/.test(entry.name)) {
      out.push(path)
    }
  }

  return out
}

const bridgeReceiver = (text: string) => {
  const bare = text.replace(/\?\./g, '.').replace(/!/g, '')

  return /(^|\.)hermesDesktop$/.test(bare) || /(^|\.)(desktop|bridge)$/.test(bare)
}

/** `key@file` for every call / member access on `keys` lacking its own `?.`. */
function unguardedUseSites(keys: Set<string>): string[] {
  const sites = new Set<string>()

  for (const file of sourceFiles(SRC)) {
    const source = parse(file)

    const visit = (node: ts.Node) => {
      if (
        ts.isPropertyAccessExpression(node) &&
        keys.has(node.name.text) &&
        bridgeReceiver(node.expression.getText())
      ) {
        const parent = node.parent

        const callsIt = ts.isCallExpression(parent) && parent.expression === node && !parent.questionDotToken

        const descends =
          (ts.isPropertyAccessExpression(parent) || ts.isElementAccessExpression(parent)) &&
          parent.expression === node &&
          !parent.questionDotToken

        if (callsIt || descends) {
          sites.add(`${node.name.text}@${relative(SRC, file)}`)
        }
      }

      ts.forEachChild(node, visit)
    }

    visit(source)
  }

  return [...sites].sort()
}

describe('hosted-web bridge drift guard', () => {
  const preload = preloadKeys()
  const declared = declaredKeys()
  const implemented = shimKeys()

  it('reads a plausible bridge (parser sanity)', () => {
    expect(preload.length).toBeGreaterThan(100)
    expect(declared.required.length).toBeGreaterThan(50)
    expect(implemented).toContain('getConnection')
  })

  it('every preload key is declared in global.d.ts', () => {
    expect(preload.filter(key => ![...declared.required, ...declared.optional].includes(key))).toEqual([])
  })

  it('the shim only defines preload keys, plus its own web-only helpers', () => {
    expect(implemented.filter(key => !preload.includes(key) && !SHIM_ONLY_KEYS.includes(key))).toEqual([])
  })

  it('every REQUIRED upstream bridge key is implemented by the shim or explicitly acknowledged absent', () => {
    const unhandled = preload
      .filter(key => declared.required.includes(key) && !implemented.includes(key))
      .filter(key => !ACKNOWLEDGED_ABSENT.includes(key))

    // New required key after an upstream sync: implement it in web-shim.ts, or
    // (if it is Electron-only and the renderer guards it) add it to
    // ACKNOWLEDGED_ABSENT. Do NOT add a catch-all no-op Proxy (see file header).
    expect(unhandled, `new required bridge keys: ${unhandled.join(', ')}`).toEqual([])
  })

  it('acknowledged-absent keys are still required, still in the preload, and still not implemented', () => {
    const stale = ACKNOWLEDGED_ABSENT.filter(
      key => !preload.includes(key) || !declared.required.includes(key) || implemented.includes(key)
    )

    expect(stale, `stale ACKNOWLEDGED_ABSENT entries: ${stale.join(', ')}`).toEqual([])
    expect([...ACKNOWLEDGED_ABSENT].sort()).toEqual(ACKNOWLEDGED_ABSENT)
  })

  it('every acknowledged-absent key that is called without `?.` has been reviewed as guarded', () => {
    const sites = unguardedUseSites(new Set(ACKNOWLEDGED_ABSENT))
    const fresh = [...new Set(sites.map(site => site.split('@')[0]))].filter(
      key => !REVIEWED_UNGUARDED_KEYS.includes(key)
    )

    // A new key here means upstream started calling an absent key without `?.`. Read the sites
    // below: if a guard precedes them add the key to REVIEWED_UNGUARDED_KEYS; if not, implement the
    // key in web-shim.ts.
    expect(fresh, `unreviewed keys, sites: ${sites.filter(s => fresh.includes(s.split('@')[0])).join(', ')}`).toEqual(
      []
    )
  })

  it('keeps the reviewed-key list honest (every entry is still an acknowledged-absent key)', () => {
    expect(REVIEWED_UNGUARDED_KEYS.filter(key => !ACKNOWLEDGED_ABSENT.includes(key))).toEqual([])
    expect([...REVIEWED_UNGUARDED_KEYS].sort()).toEqual(REVIEWED_UNGUARDED_KEYS)
  })
})
