import { Connector } from '@sailpoint/connector-sdk'

process.env.CONNECTOR_CONFIG = Buffer.from(
    JSON.stringify({ baseUrl: 'https://demo.example/v1', apiKey: 'sck_test' })
).toString('base64')

import { connector, toAccount, toEntitlement } from './index'

const rawAccount = {
    id: 'usr_1',
    userName: 'gabriel.rossi',
    displayName: 'Gabriel Rossi',
    firstName: 'Gabriel',
    lastName: 'Rossi',
    email: 'gabriel.rossi@example.com',
    department: 'IT',
    title: 'Engineer',
    manager: 'usr_0',
    employeeId: 'E1',
    location: 'Austin, TX',
    costCenter: 'CC-1',
    phone: '+1-555-0100',
    active: false,
    locked: false,
    groups: ['grp_user', 'grp_admin'],
}

describe('connector', () => {
    it('SDK major version matches Connector.SDK_VERSION', async () => {
        expect((await connector()).sdkVersion).toStrictEqual(Connector.SDK_VERSION)
    })

    it('maps an inactive demo account to disabled with every schema attribute', () => {
        const out = toAccount(rawAccount)
        expect(out.identity).toBe('usr_1')
        expect(out.disabled).toBe(true)
        expect(out.attributes.groups).toStrictEqual(['grp_user', 'grp_admin'])
        expect(Object.keys(out.attributes).sort()).toStrictEqual(
            [
                'active', 'costCenter', 'department', 'displayName', 'email', 'employeeId', 'firstName', 'groups',
                'id', 'lastName', 'location', 'locked', 'manager', 'phone', 'title', 'userName',
            ].sort()
        )
    })

    it('maps a demo group to a group entitlement with permissions', () => {
        const out = toEntitlement({
            id: 'grp_admin',
            name: 'admin',
            displayName: 'Administrator',
            description: 'Full admin',
            status: 'active',
            permissions: [{ target: 'SYSADMIN', rights: 'read,write' }],
        })
        expect(out).toMatchObject({ identity: 'grp_admin', type: 'group', deleted: false })
        expect(out.permissions).toHaveLength(1)
    })

    it('defaults missing groups and permissions to empty arrays', () => {
        expect(toAccount({ ...rawAccount, groups: undefined, active: true }).attributes.groups).toStrictEqual([])
        expect(toEntitlement({ id: 'grp_x', name: 'x' }).permissions).toStrictEqual([])
    })
})
