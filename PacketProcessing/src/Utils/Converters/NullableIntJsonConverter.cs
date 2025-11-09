using System.Text.Json;
using System.Text.Json.Serialization;

namespace PacketProcessing.Utils.Converters;

/// <summary>
/// JSON converter for nullable int that treats empty strings as null
/// </summary>
public class NullableIntJsonConverter : JsonConverter<int?>
{
    /// <summary>
    /// Reads a nullable int from JSON, converting empty strings to null
    /// </summary>
    public override int? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        if (reader.TokenType == JsonTokenType.Null)
        {
            return null;
        }

        if (reader.TokenType == JsonTokenType.String)
        {
            var stringValue = reader.GetString();
            if (string.IsNullOrWhiteSpace(stringValue))
            {
                return null;
            }

            if (int.TryParse(stringValue, out var intValue))
            {
                return intValue;
            }

            throw new JsonException($"Unable to convert \"{stringValue}\" to int?");
        }

        if (reader.TokenType == JsonTokenType.Number)
        {
            return reader.GetInt32();
        }

        throw new JsonException($"Unexpected token type {reader.TokenType} when parsing int?");
    }

    /// <summary>
    /// Writes a nullable int to JSON
    /// </summary>
    public override void Write(Utf8JsonWriter writer, int? value, JsonSerializerOptions options)
    {
        if (value.HasValue)
        {
            writer.WriteNumberValue(value.Value);
        }
        else
        {
            writer.WriteNullValue();
        }
    }
}

