import { act, cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useWebFilePicker } from './web-file-picker'

const setWebClient = (on: boolean) => {
  if (on) {
    ;(window as unknown as { __HERMES_WEB_CLIENT__?: boolean }).__HERMES_WEB_CLIENT__ = true
  } else {
    delete (window as unknown as { __HERMES_WEB_CLIENT__?: boolean }).__HERMES_WEB_CLIENT__
  }
}

function Harness({ onAttach }: { onAttach?: (files: File[]) => void }) {
  const picker = useWebFilePicker(onAttach)

  return (
    <div>
      <button data-testid="files" onClick={picker.pickFiles} type="button" />
      <button data-testid="images" onClick={picker.pickImages} type="button" />
      <output data-testid="enabled">{String(picker.enabled)}</output>
      {picker.inputs}
    </div>
  )
}

afterEach(() => {
  cleanup()
  setWebClient(false)
  vi.restoreAllMocks()
})

describe('useWebFilePicker (hosted web composer attach)', () => {
  it('is disabled and renders no inputs under Electron or without an attach handler', () => {
    const native = render(<Harness onAttach={vi.fn()} />)

    expect(native.getByTestId('enabled').textContent).toBe('false')
    expect(native.container.querySelectorAll('input[type="file"]')).toHaveLength(0)
    cleanup()

    setWebClient(true)
    const noHandler = render(<Harness />)

    expect(noHandler.getByTestId('enabled').textContent).toBe('false')
    expect(noHandler.container.querySelectorAll('input[type="file"]')).toHaveLength(0)
  })

  it('opens the chooser from a REAL click on a persistent off-screen input (keeps user activation)', () => {
    setWebClient(true)
    const click = vi.spyOn(HTMLInputElement.prototype, 'click')
    const view = render(<Harness onAttach={vi.fn()} />)
    const inputs = view.container.querySelectorAll<HTMLInputElement>('input[type="file"]')

    expect(inputs).toHaveLength(2)
    expect(inputs[0].style.position).toBe('fixed') // off-screen, NOT display:none
    expect(inputs[0].style.display).not.toBe('none')
    expect(inputs[1].accept).toBe('image/*')

    fireEvent.click(view.getByTestId('files'))
    expect(click.mock.contexts[0]).toBe(inputs[0])
    fireEvent.click(view.getByTestId('images'))
    expect(click.mock.contexts[1]).toBe(inputs[1])
  })

  it('hands the chosen File[] to onAttach once and resets the input so the same file can be re-picked', () => {
    setWebClient(true)
    const onAttach = vi.fn()
    const view = render(<Harness onAttach={onAttach} />)
    const [filesInput] = view.container.querySelectorAll<HTMLInputElement>('input[type="file"]')
    const a = new File(['a'], 'a.txt')
    const b = new File(['b'], 'b.txt')

    Object.defineProperty(filesInput, 'files', { configurable: true, value: [a, b] })
    act(() => {
      fireEvent.change(filesInput)
    })

    expect(onAttach).toHaveBeenCalledExactlyOnceWith([a, b])
    expect(filesInput.value).toBe('')

    Object.defineProperty(filesInput, 'files', { configurable: true, value: [] })
    act(() => {
      fireEvent.change(filesInput)
    })
    expect(onAttach).toHaveBeenCalledTimes(1)
  })
})
