/** 来源的业务用途由材料页与协作审阅共同解释；准备状态仍读取服务端事实。 */
export const proofSourceDescriptions = {
    DATABASE_AUDIT: '读取数据库中与本次操作一同提交的记录，核对业务字段是否改变。',
    SQLITE_OBJECTS: '确认操作是否真正创建了新数据，以及新数据属于谁。',
    SQLITE_AUDIT: '比较这份测试数据在操作前后的字段变化，只使用已提交的业务记录。',
    REFERENCE_FILE: '将本次实际收到的完整文件与已确认的参照比对。',
    MANAGED_TRANSACTION_RECORDS: '读取独立业务记录，核对本次操作是否产生对应结果。',
    CREATED_OBJECT_RECORDS: '通过独立记录确认本次创建的业务对象。',
    JSON_HTTP_RESOURCE: '读取本次资源的业务状态或指定字段，核对实际结果。',
};
