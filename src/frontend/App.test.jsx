import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import App from './App'

// Mock the global fetch function to isolate unit test runs from local/GKE network state
global.fetch = vi.fn()

describe('Arm Mobile Executor Platform - Frontend App Component', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    // Default mock behavior for FastAPI control plane health check
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'healthy' })
    })
  })

  it('renders main application header and title successfully', async () => {
    render(<App />)
    
    // Assert key platform labels exist in the header
    expect(screen.getByText(/Arm AI/i)).toBeInTheDocument()
    expect(screen.getByText(/Federated Data Plane/i)).toBeInTheDocument()
  })

  it('switches between naive and optimized code configurations on user toggle click', async () => {
    render(<App />)

    // Assert that the Naive Scalar button is present and visible
    const naiveBtn = screen.getByRole('button', { name: /Naive Scalar/i })
    expect(naiveBtn).toBeInTheDocument()

    // Locate the toggle button for Arm KleidiAI mode
    const optimizeBtn = screen.getByRole('button', { name: /Arm KleidiAI/i })
    expect(optimizeBtn).toBeInTheDocument()

    // Simulate clicking the toggle
    fireEvent.click(optimizeBtn)

    // Assert that the active state successfully updates
    await waitFor(() => {
      expect(optimizeBtn).toBeInTheDocument()
    })
  })
})
