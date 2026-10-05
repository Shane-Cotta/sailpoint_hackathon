import { ConnectorError, ConnectorErrorType } from '@sailpoint/connector-sdk'

// Replace the SDK's HTTP client with a stub so tests never hit the network.
const get = jest.fn()
jest.mock('@sailpoint/connector-sdk', () => {
    const actual = jest.requireActual('@sailpoint/connector-sdk')
    return { ...actual, createConnectorHttpClient: jest.fn(() => ({ get })) }
})

import { MyClient } from './my-client'

const config = { baseUrl: 'https://demo.example/v1', apiKey: 'sck_test' }
const httpError = (status: number) => Object.assign(new Error(`HTTP ${status}`), { response: { status } })

describe('MyClient', () => {
    beforeEach(() => get.mockReset())

    it('requires baseUrl and apiKey', () => {
        expect(() => new MyClient({})).toThrow(ConnectorError)
    })

    it('testConnection returns {} on success', async () => {
        get.mockResolvedValue({ data: { status: 'ok' } })
        expect(await new MyClient(config).testConnection()).toStrictEqual({})
        expect(get).toHaveBeenCalledWith('/health')
    })

    it('testConnection turns a 401 into a friendly ConnectorError', async () => {
        get.mockRejectedValue(httpError(401))
        await expect(new MyClient(config).testConnection()).rejects.toThrow(/rejected this key/)
    })

    it('testConnection rethrows non-401 errors', async () => {
        get.mockRejectedValue(httpError(503))
        await expect(new MyClient(config).testConnection()).rejects.toThrow('HTTP 503')
    })

    it('getAllAccounts follows the cursor until it runs out', async () => {
        get.mockResolvedValueOnce({ data: { items: [{ id: 'usr_1' }, { id: 'usr_2' }], cursor: 'c1' } })
            .mockResolvedValueOnce({ data: { items: [{ id: 'usr_3' }] } })
        const accounts = await new MyClient(config).getAllAccounts()
        expect(accounts.map((a) => a.id)).toStrictEqual(['usr_1', 'usr_2', 'usr_3'])
        expect(get).toHaveBeenLastCalledWith('/users', { params: { limit: 50, include: 'email', cursor: 'c1' } })
    })

    it('getAccount maps 404 to ConnectorErrorType.NotFound', async () => {
        get.mockRejectedValue(httpError(404))
        await expect(new MyClient(config).getAccount('usr_x')).rejects.toMatchObject({
            type: ConnectorErrorType.NotFound,
        })
    })

    it('getAccount rethrows other errors untouched', async () => {
        get.mockRejectedValue(httpError(500))
        await expect(new MyClient(config).getAccount('usr_x')).rejects.toThrow('HTTP 500')
    })

    it('getAllEntitlements asks for permissions', async () => {
        get.mockResolvedValue({ data: { items: [{ id: 'grp_1' }] } })
        expect(await new MyClient(config).getAllEntitlements()).toHaveLength(1)
        expect(get).toHaveBeenCalledWith('/groups', { params: { limit: 100, includePermissions: true } })
    })

    it('getEntitlement maps 404 to NotFound', async () => {
        get.mockRejectedValue(httpError(404))
        await expect(new MyClient(config).getEntitlement('grp_x')).rejects.toMatchObject({
            type: ConnectorErrorType.NotFound,
        })
    })
})
