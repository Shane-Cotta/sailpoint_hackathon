import {
    Context,
    createConnector,
    logger,
    readConfig,
    Response,
    SimpleKey,
    StdAccountListInput,
    StdAccountListOutput,
    StdAccountReadInput,
    StdAccountReadOutput,
    StdEntitlementListInput,
    StdEntitlementListOutput,
    StdEntitlementReadInput,
    StdEntitlementReadOutput,
    StdTestConnectionInput,
    StdTestConnectionOutput,
} from '@sailpoint/connector-sdk'
import { MyClient } from './my-client'

// Map a raw demo-API account onto the ISC account shape (every attribute declared in accountSchema).
export const toAccount = (account: any): StdAccountReadOutput => ({
    identity: account.id,
    uuid: account.id,
    disabled: !account.active,
    locked: account.locked,
    attributes: {
        id: account.id,
        userName: account.userName,
        displayName: account.displayName,
        firstName: account.firstName,
        lastName: account.lastName,
        email: account.email,
        department: account.department,
        title: account.title,
        manager: account.manager,
        employeeId: account.employeeId,
        location: account.location,
        costCenter: account.costCenter,
        phone: account.phone,
        active: account.active,
        locked: account.locked,
        groups: account.groups ?? [],
    },
})

// Map a raw demo-API group onto the ISC entitlement shape (every attribute declared in entitlementSchemas).
export const toEntitlement = (entitlement: any): StdEntitlementListOutput => ({
    identity: entitlement.id,
    uuid: entitlement.id,
    key: SimpleKey(entitlement.id),
    type: 'group',
    deleted: false,
    attributes: {
        id: entitlement.id,
        name: entitlement.name,
        displayName: entitlement.displayName,
        description: entitlement.description,
        status: entitlement.status,
        created: entitlement.created,
        updated: entitlement.updated,
    },
    permissions: entitlement.permissions ?? [],
})

// Connector must be exported as module property named connector
export const connector = async () => {
    const config = await readConfig()
    const myClient = new MyClient(config)

    return createConnector()
        .stdTestConnection(
            async (context: Context, input: StdTestConnectionInput, res: Response<StdTestConnectionOutput>) => {
                res.send(await myClient.testConnection())
            }
        )
        .stdAccountList(async (context: Context, input: StdAccountListInput, res: Response<StdAccountListOutput>) => {
            const accounts = await myClient.getAllAccounts()
            for (const account of accounts) {
                res.send(toAccount(account))
            }
            logger.info(`stdAccountList sent ${accounts.length} accounts`)
        })
        .stdAccountRead(async (context: Context, input: StdAccountReadInput, res: Response<StdAccountReadOutput>) => {
            const id = input.key && 'simple' in input.key ? input.key.simple.id : input.identity
            const account = await myClient.getAccount(id)
            res.send(toAccount(account))
        })
        .stdEntitlementList(
            async (context: Context, input: StdEntitlementListInput, res: Response<StdEntitlementListOutput>) => {
                const entitlements = await myClient.getAllEntitlements()
                for (const entitlement of entitlements) {
                    res.send(toEntitlement(entitlement))
                }
                logger.info(`stdEntitlementList sent ${entitlements.length} entitlements`)
            }
        )
        .stdEntitlementRead(
            async (context: Context, input: StdEntitlementReadInput, res: Response<StdEntitlementReadOutput>) => {
                const id = input.key && 'simple' in input.key ? input.key.simple.id : input.identity
                // std:entitlement:read output has no `deleted` flag, so drop it from the shared mapping.
                const { deleted, ...entitlement } = toEntitlement(await myClient.getEntitlement(id))
                res.send(entitlement)
            }
        )
}
