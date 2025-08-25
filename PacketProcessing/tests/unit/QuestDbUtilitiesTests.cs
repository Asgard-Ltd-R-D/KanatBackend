using PacketProcessing.Entities.Packet;
using PacketProcessing.Tests;
using PacketProcessing.Utils.QuestDB;
using Xunit;

namespace PacketProcessing.Tests.unit;

/// <summary>
/// Tests for QuestDB utilities
/// </summary>
public class QuestDbUtilitiesTests
{

    [Fact]
    public void GetTableName_ShouldReturnCorrectTableName_ForMotionPacketEntity()
    {
        // Act
        var tableName = QuestDbUtilities.GetTableName<MotionPacketEntity>();

        // Assert
        var passed = tableName == "motion_packets";
        
        TestResultLogger.LogTestResult(
            "GetTableName_ShouldReturnCorrectTableName_ForMotionPacketEntity",
            passed,
            "MotionPacketEntity type",
            "'motion_packets'",
            tableName
        );
        
        Assert.Equal("motion_packets", tableName);
    }

    [Fact]
    public void GetTableName_ShouldReturnCorrectTableName_ForOnVIFPacketEntity()
    {
        // Act
        var tableName = QuestDbUtilities.GetTableName<OnVIFPacketEntity>();

        // Assert
        var passed = tableName == "onvif_packets";
        
        TestResultLogger.LogTestResult(
            "GetTableName_ShouldReturnCorrectTableName_ForOnVIFPacketEntity",
            passed,
            "OnVIFPacketEntity type",
            "'onvif_packets'",
            tableName
        );
        
        Assert.Equal("onvif_packets", tableName);
    }

    [Fact]
    public void GetTableName_ShouldReturnCorrectTableName_ForSafetyPacketEntity()
    {
        // Act
        var tableName = QuestDbUtilities.GetTableName<SafetyPacketEntity>();

        // Assert
        var passed = tableName == "safety_packets";
        
        TestResultLogger.LogTestResult(
            "GetTableName_ShouldReturnCorrectTableName_ForSafetyPacketEntity",
            passed,
            "SafetyPacketEntity type",
            "'safety_packets'",
            tableName
        );
        
        Assert.Equal("safety_packets", tableName);
    }

    [Fact]
    public void GetTableName_ShouldReturnConsistentResults()
    {
        // Act
        var tableName1 = QuestDbUtilities.GetTableName<MotionPacketEntity>();
        var tableName2 = QuestDbUtilities.GetTableName<MotionPacketEntity>();
        var tableName3 = QuestDbUtilities.GetTableName<MotionPacketEntity>();

        // Assert
        var isConsistent = tableName1 == tableName2 && tableName2 == tableName3;
        
        TestResultLogger.LogTestResult(
            "GetTableName_ShouldReturnConsistentResults",
            isConsistent,
            "Multiple calls to GetTableName for same entity type",
            "Same table name for each call",
            $"Table1={tableName1}, Table2={tableName2}, Table3={tableName3}"
        );
        
        Assert.Equal(tableName1, tableName2);
        Assert.Equal(tableName2, tableName3);
        Assert.Equal("motion_packets", tableName1);
    }
}
