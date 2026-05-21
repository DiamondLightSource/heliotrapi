# Frontend Smart Input Types

The web frontend now intelligently adapts input fields based on parameter types.

## Supported Input Types

### Primitive Types
- **int** → Number input (`<input type="number">`)
- **float** → Number input with decimal support
- **str** → Text input
- **bool** → Checkbox input
- **Any** → Smart detection with JSON fallback

### Sequence/Array Types
- **list** → Textarea for comma-separated or JSON array input
- **sequence** → Textarea for array values
- **np.ndarray** → Textarea for numpy array values
- **array** → Textarea for array values

### Complex Types
- **dict** → JSON textarea for object/dictionary input
- **object** → JSON textarea
- **Any (with JSON)** → JSON textarea for complex objects

## Input Formats

### Array/List Inputs
Users can enter values in multiple formats:

```
Comma-separated:
1.0, 2.5, 3.7, 4.2

JSON array:
[1.0, 2.5, 3.7, 4.2]

Newline-separated:
1.0
2.5
3.7
4.2
```

The frontend automatically detects the format and parses accordingly.

### JSON Inputs
For complex types, enter valid JSON:
```json
{"key": "value", "nested": {"data": 123}}
```

## Type Conversion

The frontend automatically:
1. **Detects** the parameter type from the annotation
2. **Renders** the appropriate UI element
3. **Parses** the input in the correct format
4. **Validates** the input and shows helpful error messages
5. **Converts** to the correct Python type before sending to the API

## Error Handling

- **Invalid integers** → Shows clear error message
- **Invalid floats** → Prevents invalid number submission
- **Malformed JSON** → Shows JSON parsing error
- **Empty arrays** → Alerts user to provide values
- **Type mismatches** → Helpful feedback on what format is expected

## Examples

### Submitting a list of floats
Parameter: `values: list`
1. Frontend shows textarea
2. User enters: `1.5, 2.7, 3.2`
3. Frontend converts to: `[1.5, 2.7, 3.2]`
4. Sends to API as JSON array

### Submitting an integer
Parameter: `count: int`
1. Frontend shows number input
2. User enters: `42`
3. Frontend converts to: `42` (integer)
4. Sends to API as integer

### Submitting a boolean
Parameter: `enabled: bool`
1. Frontend shows checkbox
2. User checks/unchecks
3. Frontend converts to: `true` or `false`
4. Sends to API as boolean

### Submitting complex object
Parameter: `config: dict`
1. Frontend shows JSON textarea
2. User enters: `{"learning_rate": 0.01, "epochs": 100}`
3. Frontend validates JSON
4. Sends to API as JSON object
