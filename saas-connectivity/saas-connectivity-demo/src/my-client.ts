import { AxiosInstance, ConnectorError, ConnectorErrorType, createConnectorHttpClient } from '@sailpoint/connector-sdk'

/**
 * Thin HTTP client for the SaaS Connectivity Demo API.
 * Every call is a relative path off the configured baseUrl, authenticated with the demo API key.
 */
export class MyClient {
    private readonly httpClient: AxiosInstance

    constructor(config: any) {
        if (!config?.baseUrl || !config?.apiKey) {
            throw new ConnectorError('baseUrl and apiKey must be provided from config')
        }
        this.httpClient = createConnectorHttpClient({
            baseURL: config.baseUrl,
            auth: { type: 'bearer', token: config.apiKey },
        })
    }

    // GET /health is authenticated on purpose, so a bad key fails the test.
    async testConnection(): Promise<any> {
        try {
            await this.httpClient.get('/health')
            return {}
        } catch (error: any) {
            if (error?.response?.status === 401) {
                throw new ConnectorError('The demo API rejected this key. Demo keys expire after 7 days.')
            }
            throw error
        }
    }

    // The demo API paginates by opaque cursor, so keep going until there isn't one.
    async getAllAccounts(): Promise<any[]> {
        const accounts: any[] = []
        let cursor: string | undefined
        do {
            const params: any = { limit: 50, include: 'email' }
            if (cursor) {
                params.cursor = cursor
            }
            const response = await this.httpClient.get('/users', { params })
            accounts.push(...response.data.items)
            cursor = response.data.cursor
        } while (cursor)
        return accounts
    }

    async getAccount(id: string): Promise<any> {
        try {
            const response = await this.httpClient.get(`/users/${encodeURIComponent(id)}`, {
                params: { include: 'email' },
            })
            return response.data
        } catch (error: any) {
            // Let ISC fall through to std:account:create when the account is gone.
            if (error?.response?.status === 404) {
                throw new ConnectorError(`Account ${id} not found`, ConnectorErrorType.NotFound)
            }
            throw error
        }
    }

    // All 8 groups fit in one page at limit=100, so no cursor loop is needed.
    async getAllEntitlements(): Promise<any[]> {
        const response = await this.httpClient.get('/groups', {
            params: { limit: 100, includePermissions: true },
        })
        return response.data.items
    }

    // Not in the guide: the spec declares std:entitlement:read, so we implement it too.
    async getEntitlement(id: string): Promise<any> {
        try {
            const response = await this.httpClient.get(`/groups/${encodeURIComponent(id)}`, {
                params: { includePermissions: true },
            })
            return response.data
        } catch (error: any) {
            if (error?.response?.status === 404) {
                throw new ConnectorError(`Entitlement ${id} not found`, ConnectorErrorType.NotFound)
            }
            throw error
        }
    }
}
