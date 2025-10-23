using Xunit;

namespace PacketProcessing.IntegrationTests;

/// <summary>
/// Collection definition for integration tests to share the WebApplicationFactory
/// </summary>
[CollectionDefinition("IntegrationTestCollection")]
public class IntegrationTestCollection : ICollectionFixture<SharedWebApplicationFactory>
{
    // This class has no code, and is never created. Its purpose is simply
    // to be the place to apply [CollectionDefinition] and all the
    // ICollectionFixture<> interfaces.
}
